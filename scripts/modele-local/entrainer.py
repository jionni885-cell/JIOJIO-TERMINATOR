"""Entraine un VRAI petit modele de langage, ici, sans cle et sans reseau.

POURQUOI CE SCRIPT EXISTE. Tous les rapports de ce depot portent la meme reserve, ecrite en
clair : « le modele est SIMULE ». C'est honnete, mais ca laisse une question ouverte — le
harness tient-il quand le modele qui repond n'est pas notre propre simulation ? Une simulation
dont on a choisi le taux d'erreur ne peut pas repondre a cette question, par construction : on
mesure ce qu'on a mis dedans.

Ici, le modele est REEEL au sens strict : des poids, un vrai calcul, une vraie distribution de
sortie, et des erreurs que PERSONNE n'a modelisees. Il est petit — c'est assume et declare :
ce n'est pas un substitut a un modele frontier,e c'est un modele dont les erreurs sont
authentiques, ce qui suffit a mettre le harness a l'epreuve.

D'ou vient l'architecture : le transformeur decodeur char-level decrit par `karpathy/nanoGPT`
(et son ancetre `karpathy/minGPT`). Le code ci-dessous est ecrit ici — court, lisible, sans
dependance autre que PyTorch — mais l'idee n'est pas de nous : un bloc de self-attention
causal, des embeddings de position appris, une tete de langage sur le dernier etat cache.
Le corpus est le meilleur disponible sur cette machine : le code de CE depot.

Ce qu'on obtient a la fin : `modele.pt`, chargeable par `serveur.py`, qui expose une API
compatible OpenAI — donc branchable sur `jio` par `JIO_OLLAMA`, sans toucher au harness.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import time

import torch
import torch.nn as nn
from torch.nn import functional as F


class BlocAttention(nn.Module):
    """Self-attention causale multi-tetes — la brique de base du transformeur decodeur.

    « Causale » : chaque position ne voit QUE ce qui la precede. C'est la seule facon
    d'entrainer un modele a predire la suite d'un texte sans tricher en lisant la reponse.
    """

    def __init__(self, n_emb: int, n_tetes: int, bloc: int, dropout: float) -> None:
        super().__init__()
        assert n_emb % n_tetes == 0
        self.n_tetes = n_tetes
        self.tete_dim = n_emb // n_tetes
        self.projection = nn.Linear(n_emb, 3 * n_emb)
        self.sortie = nn.Linear(n_emb, n_emb)
        self.dropout = nn.Dropout(dropout)
        # `persistent=False` : le masque est une CONSTANTE, pas un poids appris. Sans cette
        # ligne il part dans le `state_dict`, et la mesure l'a montre tout de suite : un
        # modele de 251 904 parametres produisait un fichier de 135 Mo, parce qu'un masque
        # 4096x4096 etait sauvegarde dans CHAQUE bloc. La taille d'un modele doit dire le
        # nombre de ses parametres, sinon le fichier raconte autre chose que ce qu'il est.
        self.register_buffer(
            "masque",
            torch.tril(torch.ones(bloc, bloc)).view(1, 1, bloc, bloc),
            persistent=False,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, T, C = x.shape
        q, k, v = self.projection(x).split(C, dim=2)
        q = q.view(B, T, self.n_tetes, self.tete_dim).transpose(1, 2)
        k = k.view(B, T, self.n_tetes, self.tete_dim).transpose(1, 2)
        v = v.view(B, T, self.n_tetes, self.tete_dim).transpose(1, 2)
        poids = (q @ k.transpose(-2, -1)) / math.sqrt(self.tete_dim)
        poids = poids.masked_fill(self.masque[:, :, :T, :T] == 0, float("-inf"))
        poids = self.dropout(F.softmax(poids, dim=-1))
        y = (poids @ v).transpose(1, 2).contiguous().view(B, T, C)
        return self.dropout(self.sortie(y))


class Bloc(nn.Module):
    """Un bloc du transformeur : attention puis reseau avant, avec connexions residuelles."""

    def __init__(self, n_emb: int, n_tetes: int, bloc: int, dropout: float) -> None:
        super().__init__()
        self.norme1 = nn.LayerNorm(n_emb)
        self.attention = BlocAttention(n_emb, n_tetes, bloc, dropout)
        self.norme2 = nn.LayerNorm(n_emb)
        self.avant = nn.Sequential(
            nn.Linear(n_emb, 4 * n_emb), nn.GELU(), nn.Linear(4 * n_emb, n_emb),
            nn.Dropout(dropout),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attention(self.norme1(x))
        return x + self.avant(self.norme2(x))


class ModeleDeCode(nn.Module):
    """Un modele de langage caractere par caractere, entraine sur du code Python."""

    def __init__(
        self, taille_vocab: int, n_emb: int, n_tetes: int, n_couches: int,
        bloc: int, dropout: float,
    ) -> None:
        super().__init__()
        self.bloc = bloc
        self.embedding = nn.Embedding(taille_vocab, n_emb)
        self.position = nn.Embedding(bloc, n_emb)
        self.blocs = nn.Sequential(
            *[Bloc(n_emb, n_tetes, bloc, dropout) for _ in range(n_couches)]
        )
        self.norme_finale = nn.LayerNorm(n_emb)
        self.tete = nn.Linear(n_emb, taille_vocab, bias=False)
        self.apply(self._init)

    def _init(self, module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, idx: torch.Tensor, cibles: torch.Tensor | None = None):
        B, T = idx.shape
        x = self.embedding(idx) + self.position(torch.arange(T, device=idx.device))
        x = self.norme_finale(self.blocs(x))
        if cibles is None:
            return self.tete(x[:, [-1], :]), None
        logits = self.tete(x)
        perte = F.cross_entropy(logits.view(-1, logits.size(-1)), cibles.reshape(-1))
        return logits, perte

    def nombre_de_parametres(self) -> int:
        return sum(p.numel() for p in self.parameters())

    @torch.no_grad()
    def generer(
        self, idx: torch.Tensor, max_nouveaux: int, temperature: float = 1.0,
        top_k: int | None = None, graine: int | None = None,
    ) -> torch.Tensor:
        """Genere la suite, un caractere a la fois — temperature et top_k compris."""
        if graine is not None:
            torch.manual_seed(graine)
        for _ in range(max_nouveaux):
            idx_cond = idx[:, -self.bloc:]
            logits, _ = self(idx_cond)
            logits = logits[:, -1, :] / max(temperature, 1e-6)
            if top_k is not None:
                seuil = torch.topk(logits, min(top_k, logits.size(-1)))[0][:, [-1]]
                logits = torch.where(logits < seuil, float("-inf"), logits)
            probas = F.softmax(logits, dim=-1)
            idx = torch.cat([idx, torch.multinomial(probas, num_samples=1)], dim=1)
        return idx


def _corpus(racine: pathlib.Path, plafond: int) -> str:
    """Le corpus : le code Python du depot, tous fichiers confondus, ordre melange.

    Deux corrections, toutes deux trouvees a la premiere execution — et la seconde est un
    defaut de METHODE, pas de code :

      * la premiere version prenait `jio/**/*.py` dans l'ordre alphabetique et s'arretait au
        plafond : elle n'entrainait donc que sur les **8 premiers fichiers** du paquet, jamais
        sur les tests ni les scripts. Un corpus annonce a 500 000 caracteres qui ne voit que
        1 % des fichiers du depot, c'est un modele qui apprend un fichier, pas un langage ;
      * chaque fichier etait tronque a ses 60 000 premiers caracteres, ce qui coupe un fichier
        au milieu d'une fonction : le modele apprend alors des suites qui n'existent pas.

    L'ordre est desormais melange avec une GRAINE (donc reproductible) et chaque fichier est
    pris en entier : le modele voit des fonctions completes, terminees, dans un ordre qui ne
    lui permet pas de memoriser la sequence des fichiers.
    """
    import random as _random

    fichiers: list[pathlib.Path] = []
    for motif in ("jio/**/*.py", "tests/**/*.py", "scripts/**/*.py"):
        for chemin in racine.glob(motif):
            if "__pycache__" in chemin.parts or "modele-local" in chemin.parts:
                continue
            if chemin.is_file():
                fichiers.append(chemin)
    _random.Random(20260930).shuffle(fichiers)

    morceaux: list[str] = []
    total = 0
    for chemin in fichiers:
        texte = chemin.read_text(encoding="utf-8", errors="replace")
        morceaux.append(texte)
        total += len(texte) + 2
        if total >= plafond:
            break
    return "\n\n".join(morceaux)[:plafond]


def main() -> int:
    parseur = argparse.ArgumentParser(description="Entraine un petit modele de code, localement.")
    parseur.add_argument("--sortie", default="modele/modele.pt")
    parseur.add_argument("--corpus-octets", type=int, default=600_000)
    parseur.add_argument("--iterations", type=int, default=2500)
    parseur.add_argument("--bloc", type=int, default=192)
    parseur.add_argument("--batch", type=int, default=24)
    parseur.add_argument("--n-emb", type=int, default=192)
    parseur.add_argument("--n-tetes", type=int, default=6)
    parseur.add_argument("--n-couches", type=int, default=4)
    parseur.add_argument("--dropout", type=float, default=0.1)
    parseur.add_argument("--lr", type=float, default=3e-3)
    parseur.add_argument("--graine", type=int, default=1337)
    parseur.add_argument("--eval-toutes", type=int, default=250)
    args = parseur.parse_args()

    torch.manual_seed(args.graine)
    racine = pathlib.Path(__file__).resolve().parents[2]
    texte = _corpus(racine, args.corpus_octets)
    alphabet = sorted(set(texte))
    stoi = {c: i for i, c in enumerate(alphabet)}
    donnees = torch.tensor([stoi[c] for c in texte], dtype=torch.long)
    coupe = int(len(donnees) * 0.9)
    entrainement, validation = donnees[:coupe], donnees[coupe:]

    print(f"  corpus        : {len(texte)} caracteres  ·  vocabulaire {len(alphabet)}")
    print(f"  entrainement  : {len(entrainement)}  ·  validation {len(validation)}")

    def lot(source: torch.Tensor):
        idx = torch.randint(len(source) - args.bloc - 1, (args.batch,))
        x = torch.stack([source[i : i + args.bloc] for i in idx])
        y = torch.stack([source[i + 1 : i + args.bloc + 1] for i in idx])
        return x, y

    modele = ModeleDeCode(
        len(alphabet), args.n_emb, args.n_tetes, args.n_couches, args.bloc, args.dropout
    )
    print(f"  parametres    : {modele.nombre_de_parametres():,}".replace(",", " "))
    optimiseur = torch.optim.AdamW(modele.parameters(), lr=args.lr, betas=(0.9, 0.95))

    @torch.no_grad()
    def perte_validation(essais: int = 20) -> float:
        modele.eval()
        valeurs = [modele(*lot(validation))[1].item() for _ in range(essais)]
        modele.train()
        return sum(valeurs) / len(valeurs)

    depart = time.monotonic()
    for etape in range(1, args.iterations + 1):
        x, y = lot(entrainement)
        _, perte = modele(x, y)
        optimiseur.zero_grad(set_to_none=True)
        perte.backward()
        torch.nn.utils.clip_grad_norm_(modele.parameters(), 1.0)
        optimiseur.step()
        if etape % args.eval_toutes == 0 or etape == args.iterations:
            val = perte_validation()
            ecoule = time.monotonic() - depart
            print(
                f"  etape {etape:>5}/{args.iterations}  perte {perte.item():.3f}  "
                f"validation {val:.3f}  {ecoule:5.0f}s"
            )

    destination = pathlib.Path(args.sortie)
    if not destination.is_absolute():
        destination = racine / destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "poids": modele.state_dict(),
            "alphabet": alphabet,
            "config": {
                "bloc": args.bloc, "n_emb": args.n_emb, "n_tetes": args.n_tetes,
                "n_couches": args.n_couches, "dropout": 0.0,
            },
            "corpus_octets": len(texte),
            "parametres": modele.nombre_de_parametres(),
            "validation": perte_validation(essais=40),
            "graine": args.graine,
        },
        destination,
    )
    print(f"  modele ecrit  : {destination}  ({destination.stat().st_size / 1e6:.1f} Mo)")
    print(json.dumps({"modele": str(destination), "parametres": modele.nombre_de_parametres()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
