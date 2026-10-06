"""Add slide transitions to a generated deck.

pptxgenjs cannot write transitions, so they are injected into the packed XML
afterwards. Transitions are the one piece of PowerPoint motion that is both
well-understood and safe to hand-write: a single element per slide, with a
documented fallback for older renderers.

Entrance builds are deliberately *not* generated here. A <p:timing> timeline is
long, easy to malform, and a malformed one makes PowerPoint declare the file
corrupt -- and with no renderer on this machine it could not be verified before
being handed over. Adding builds in PowerPoint is two clicks; shipping a deck
that will not open is not worth saving them.

    python add_motion.py deck.pptx
"""

from __future__ import annotations

import re
import shutil
import sys
import zipfile
from pathlib import Path

#: Which transition each slide gets, by position. Section openers push, content
#: fades, so movement marks a change of topic rather than happening constantly.
PUSH = 'push'
FADE = 'fade'
MORPH = 'morph'


def transition_xml(kind: str, ms: int = 700) -> str:
    """One transition element, with a fallback for renderers predating 2010."""
    if kind == PUSH:
        modern = '<p14:push dir="u"/>'
        legacy = '<p:push dir="u"/>'
    elif kind == MORPH:
        # Morph needs p159; fall back to a fade where it is unsupported.
        modern = '<p159:morph option="byObject"/>'
        legacy = '<p:fade/>'
    else:
        modern = '<p14:fade/>'
        legacy = '<p:fade/>'

    requires = 'p159' if kind == MORPH else 'p14'
    ns = (' xmlns:p159="http://schemas.microsoft.com/office/powerpoint/2015/09/main"'
          if kind == MORPH else '')

    return (
        '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/'
        'markup-compatibility/2006">'
        f'<mc:Choice xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main"'
        f'{ns} Requires="{requires}">'
        f'<p:transition spd="slow" p14:dur="{ms}">{modern}</p:transition>'
        '</mc:Choice>'
        '<mc:Fallback>'
        f'<p:transition spd="slow">{legacy}</p:transition>'
        '</mc:Fallback>'
        '</mc:AlternateContent>'
    )


def plan(count: int) -> dict[int, str]:
    """Title and closing slides push; everything else fades."""
    choices = {}
    for i in range(1, count + 1):
        if i == 1 or i == count:
            choices[i] = PUSH
        else:
            choices[i] = FADE
    return choices


def apply(path: Path) -> int:
    backup = path.with_suffix('.pptx.bak')
    shutil.copy2(path, backup)

    with zipfile.ZipFile(path) as zin:
        items = {n: zin.read(n) for n in zin.namelist()}

    slides = sorted(
        (n for n in items if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)),
        key=lambda n: int(re.search(r'(\d+)', n.split('/')[-1]).group(1)),
    )
    choices = plan(len(slides))

    changed = 0
    for idx, name in enumerate(slides, start=1):
        xml = items[name].decode('utf-8')
        if '<p:transition' in xml or 'mc:AlternateContent' in xml:
            continue
        # The transition sits inside <p:sld>, after the slide's content.
        if '</p:sld>' not in xml:
            print(f'  skipped {name}: unexpected structure')
            continue
        xml = xml.replace('</p:sld>', transition_xml(choices[idx]) + '</p:sld>')
        items[name] = xml.encode('utf-8')
        changed += 1

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for name, data in items.items():
            zout.writestr(name, data)

    print(f'{changed} slide(s) given transitions in {path.name}')
    print(f'backup kept at {backup.name}')
    return changed


if __name__ == '__main__':
    target = Path(sys.argv[1] if len(sys.argv) > 1 else 'SmartTraffic-5min.pptx')
    if not target.exists():
        raise SystemExit(f'no such deck: {target}')
    apply(target)
