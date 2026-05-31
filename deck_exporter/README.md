# Moxfield Deck Exporter

Converts Moxfield deck IDs to Forge- or XMage-compatible `.dck` files.

## Usage

```bash
python moxfield_deck_exporter.py DECK_ID [DECK_ID ...] [options]
```

### Arguments

- `DECK_ID`: One or more Moxfield deck IDs to convert

### Options

- `--format, -f {forge,xmage}`: Output format (default: forge)
- `--output-dir, -o DIR`: Output directory for .dck files. Forge default: `%APPDATA%/Forge/decks/commander`. XMage default: `~/Documents/xmage_decks`
- `--no-override, -n`: Prompt before overriding existing .dck files (default: override without prompting)

## Examples

### Convert a single deck to the default Forge directory
```bash
python moxfield_deck_exporter.py i5YKOQsfIk6rsBMfQZ1RUw
```

### Convert a deck to XMage format
```bash
python moxfield_deck_exporter.py i5YKOQsfIk6rsBMfQZ1RUw --format xmage
```

### Convert to a custom directory
```bash
python moxfield_deck_exporter.py i5YKOQsfIk6rsBMfQZ1RUw --output-dir C:\CustomDecks
```

### Prompt before overriding existing files
```bash
python moxfield_deck_exporter.py i5YKOQsfIk6rsBMfQZ1RUw --no-override
```

## Output Format

For Forge output, generated `.dck` files have the following format:

```
[metadata]
name=<deck name>

[Main]
<mainboard cards>

[Commander]
<commander cards>

[Sideboard]
<sideboard cards>
```

- Empty sections are omitted
- Card format: `<quantity> <card name>` (one per line)
- Cards are sorted alphabetically by name

For XMage output, generated `.dck` files list each card as:

```
<quantity> [SET:CN] <card name>
```

Sideboard cards are prefixed with `SB:`:

```
SB: <quantity> [SET:CN] <card name>
```

## File Naming

- Output files are named `<deck_name>.dck`
- Invalid filename characters are replaced with underscores
