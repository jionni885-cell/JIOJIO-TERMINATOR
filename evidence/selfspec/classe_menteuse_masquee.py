# jio:corpus-fautif : fichier de preuve, fautif a DESSEIN.
class Compteur:
    """Un compteur qui part de zero et ne peut pas devenir negatif.

    >>> c = Compteur()
    >>> c.valeur
    0
    >>> c.ajouter(-5)
    >>> c.valeur
    0
    """
    def __init__(self):
        self.valeur = 0

    def ajouter(self, n):
        self.valeur += n
        return self.valeur
