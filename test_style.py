from prompt_toolkit.styles import Style
try:
    s = Style.from_dict({'bottom-toolbar': 'noreverse bg:default fg:default'})
    print("noreverse valid")
except Exception as e:
    print(e)
