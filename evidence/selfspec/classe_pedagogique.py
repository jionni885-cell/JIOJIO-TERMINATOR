class Journal:
    """Journal de texte, pedagogique : les exemples MENTIONNENT des appels sans
    annoncer de sortie. C'est une docstring d'illustration, pas une specification,
    et elle ne doit donc produire ni accusation ni reserve.

    >>> Journal.logger(8080)
    >>> Journal.afficher("bonjour")
    """

    def logger(port):
        print("Connexion au port", port)

    def afficher(texte):
        print(texte)
