# Penguin

Pre-delivery quality control for eDiscovery productions.

A production goes out the door as three things that have to agree with each
other: a metadata load file, an image load file, and a folder of natives and
extracted text. When they disagree, someone finds out later — usually opposing
counsel, usually in writing. Penguin reads all three and reports where they
disagree before the volume ships.

It runs offline, has no dependencies outside the standard library, and does not
modify the production.

## What it checks

| Rule | Severity | What it catches |
| --- | --- | --- |
| `required-field` | blocker | Load file is missing a column the protocol requires |
| `bates-missing` | blocker | A record carries no beginning Bates number |
| `bates-malformed` | blocker | A Bates value does not end in a numeric sequence |
| `bates-duplicate` | blocker | The same Bates number is used twice |
| `bates-range` | blocker | EndDoc precedes BegDoc, or the prefixes differ |
| `bates-gap` | warning | The range skips numbers no document accounts for |
| `family-orphan` | blocker | An attachment points at a parent not in the production |
| `family-order` | warning | A child document sorts before its parent |
| `family-range` | blocker | A family range does not enclose its own document |
| `native-missing` | blocker | A native named in the load file is not in the volume |
| `text-missing` | blocker | An extracted text file is not in the volume |
| `text-empty` | warning | Extraction produced a zero-byte file |
| `image-orphan` | blocker | The OPT references a document the DAT does not contain |
| `image-missing` | blocker | A document states pages but has no images |
| `page-count` | blocker | Stated page count disagrees with the image load file |
| `date-format` | warning | A date did not parse in any expected format |
| `control-character` | blocker | A field carries an unescaped control character |
| `endorsement-missing` | blocker | A designated document has no endorsement text |

Blockers stop delivery. Warnings need a documented decision, not necessarily a fix.

### Bates gaps, specifically

Gap detection expands each document's full BegDoc-to-EndDoc range before
looking for breaks. Comparing consecutive BegDoc values instead — the obvious
implementation — reports every multi-page document as a gap, which trains
reviewers to ignore the warning. On the sample volume that difference is 30
false gaps versus the one real one.

## Search term reporting

Point it at a term list and it scores each term against the production's
extracted text:

- **Documents** — how many documents the term hits
- **Unique** — how many of those no other term on the list reaches
- **Corpus** — the share of searched documents the term touches

Unique hits are the number that matters when a term list is being negotiated. A
term with no unique hits is one you can concede. A term touching half the corpus
is not a search term, it is an argument for a different approach.

Wildcards are the ones analysts actually type: `*` for any run of characters,
`?` for one. Everything else is escaped, so `profit & loss` is safe to pass.

## Install

```bash
git clone https://github.com/axlAJ/penguin.git
cd penguin
pip install -e .
```

Python 3.10 or later. No runtime dependencies.

## Use

```bash
penguin run \
  --dat VOL001/VOL001.dat \
  --opt VOL001/VOL001.opt \
  --volume VOL001 \
  --terms terms.txt \
  --html qc-report.html \
  --csv exceptions.csv
```

Exit code is 1 when a blocking defect is found, so it drops into a delivery
pipeline as a gate. `--fail-on any` fails on warnings too; `--fail-on never`
always exits 0 and just reports.

Other options:

- `--encoding` — productions arrive as UTF-16 and Windows-1252 as often as UTF-8
- `--require` — override the default required-column list for a given protocol

## Try it on sample data

The repository ships a generator that builds a synthetic 60-document
production with eight defects deliberately seeded into it. No real data is
included and none is needed.

```bash
python -m sample.make_sample sample/VOL001
penguin run --dat sample/VOL001/VOL001.dat --opt sample/VOL001/VOL001.opt \
  --volume sample/VOL001 --terms sample/VOL001/terms.txt --html report.html
```

Expected output:

```
Records        60
Bates          NBRG-0000001 to NBRG-0000122
Pages          120
Natives        59 of 60 present
Text           60 of 60 present
Blocking       5
To review      3
```

The five blockers are a missing native, an attachment whose parent was
withheld, an image set for a document pulled from the DAT late, a page count
that drifted, and a document designated confidential without endorsement text.

## Development

```bash
pip install -e ".[dev]"
pytest
```

39 tests covering the parsers, every rule, the search term scoring, and the
CLI end to end.

## Scope

This validates structure and internal consistency. It does not make privilege
calls, does not decide what is responsive, and does not replace a reviewer
looking at documents. It catches the mechanical failures that waste a review
team's afternoon and occasionally cost a client a re-production.

## Licence

MIT.
