"""Use the same remaining-PSD verification on scene29's actual selected direction."""
from pathlib import Path
source=Path(__file__).with_name('verify_effectcraft_remaining_psds.py').read_text(encoding='utf8')
replacements={
 "psd-3376-remaining-20261021":"psd-3376-current29-20261021",
 "CASES={'19-current-3s':'c5edad20c4799c05','19-oneway-7s':'9574ad511c54fe00','19-sustained-7s':'0a40698ba4820282'}":"CASES={'29-current-sustained':'cb5d139b6489f841'}",
 "'3376-019-effect-'":"'3376-029-effect-'",
 "remaining19, three archived direction versions":"current selected scene29 sustained direction",
}
for before,after in replacements.items():
    assert source.count(before)==1,before
    source=source.replace(before,after)
exec(compile(source,str(Path(__file__).with_name('verify_effectcraft_remaining_psds.py')),'exec'))
