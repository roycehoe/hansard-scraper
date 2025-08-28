from typing import Optional




def get_start_of_speech_line(
    markdown_content: str, title: str, subtitle: Optional[str], id: int
) -> Optional[int]:
    for i, line in enumerate(markdown_content.splitlines()):
        if subtitle:
            if subtitle in line:
                return i
        if title in line:
            return i
    print(id)
    return None