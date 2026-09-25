class Pile:
    """Pile LIFO : le dernier empile est le premier depile.

    >>> p = Pile()
    >>> p.empiler(1)
    >>> p.empiler(2)
    >>> p.depiler()
    2
    """
    def __init__(self):
        self._items = []

    def empiler(self, x):
        self._items.append(x)

    def depiler(self):
        return self._items.pop(0)
