# utils/input_buffer.py

class InputBuffer:
    def __init__(self):
        self.buffer = []
        self.position = 0

    def add(self, text: str):
        text = text.strip()
        if not text:
            return
        if text in self.buffer:
            self.buffer.remove(text)  # Duplikat löschen
        self.buffer.append(text)
        self.position = len(self.buffer)  # Neue Eingabe, also "nach dem letzten"

    def back(self) -> str:
        if self.position > 0:
            self.position -= 1
        return self.buffer[self.position] if self.buffer else ""

    def forward(self) -> str:
        if self.position < len(self.buffer) - 1:
            self.position += 1
            return self.buffer[self.position]
        else:
            self.position = len(self.buffer)
            return ""

    def reset_position(self):
        self.position = len(self.buffer)
