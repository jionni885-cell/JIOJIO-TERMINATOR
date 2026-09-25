class Compteur:
    """Un compteur qui part de zero.

    >>> c = Compteur()
    >>> c.ajouter(3)
    3
    """
    def __init__(self):
        self.valeur = 0

    def ajouter(self, n):
        self.valeur += n
        return self.valeur
