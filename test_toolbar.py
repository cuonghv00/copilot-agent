import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
import shutil

TOOLBAR_STYLE = Style.from_dict({
    'bottom-toolbar': 'noreverse bg:default fg:default',
})

def get_toolbar():
    left_text = f'<style fg="ansigreen">●</style> <style fg="ansiyellow">[sonnet]</style> /new   /model   /help   /exit'
    left_plain = f'● [sonnet] /new   /model   /help   /exit'
    
    sid = "a0be4ed0-ed8c-4fb3-ba05-330684119caa"
    out_flag = ''
    right_plain = f'session: {sid}'
    
    term_width = shutil.get_terminal_size().columns
    content_width = term_width - 4 
    pad_len = content_width - len(left_plain) - len(right_plain)
    if pad_len < 1:
        pad_len = 1
    pad = " " * pad_len
    
    top_line = "─" * (term_width - 2)
    bottom_line = "─" * (term_width - 2)
    
    return HTML(
        f'<style fg="ansiblue">╭{top_line}╮</style>\n'
        f'<style fg="ansiblue">│</style> {left_text}{pad}<style fg="ansicyan">session: {sid}</style>{out_flag} <style fg="ansiblue">│</style>\n'
        f'<style fg="ansiblue">╰{bottom_line}╯</style>'
    )

async def main():
    session = PromptSession(style=TOOLBAR_STYLE)
    await session.prompt_async("❯ ", bottom_toolbar=get_toolbar)

if __name__ == "__main__":
    asyncio.run(main())
