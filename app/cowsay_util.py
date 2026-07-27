import cowsay


def render(text: str, character: str = "cow") -> str:
    return cowsay.get_output_string(character, text)
