"""A simple back-only stack of navigation views."""


class NavigationHistory:
    def __init__(self):
        self._stack = []

    def push(self, view):
        self._stack.append(view)

    def pop(self):
        if not self._stack:
            return None
        return self._stack.pop()
