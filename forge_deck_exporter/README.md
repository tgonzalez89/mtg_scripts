# Moxfield to Forge Deck Exporter

Converts Moxfield deck IDs to Forge-compatible `.dck` files.

## Usage

```bash
python moxfield_to_forge.py DECK_ID [DECK_ID ...] [options]
```

### Arguments

- `DECK_ID`: One or more Moxfield deck IDs to convert

### Options

- `--output-dir, -o DIR`: Output directory for .dck files (default: `%APPDATA%/Forge/decks/commander`)
- `--no-override, -n`: Prompt before overriding existing .dck files (default: override without prompting)

## Examples

### Convert a single deck to the default Forge directory
```bash
python moxfield_to_forge.py i5YKOQsfIk6rsBMfQZ1RUw
```

### Convert multiple decks
```bash
python moxfield_to_forge.py i5YKOQsfIk6rsBMfQZ1RUw w8D7qgKlSEOPLo9r0QJDWw
```

### Convert to a custom directory
```bash
python moxfield_to_forge.py i5YKOQsfIk6rsBMfQZ1RUw --output-dir C:\CustomDecks
```

### Prompt before overriding existing files
```bash
python moxfield_to_forge.py i5YKOQsfIk6rsBMfQZ1RUw --no-override
```

## Output Format

Generated `.dck` files have the following format:

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

## File Naming

- Output files are named `<deck_name>.dck`
- Invalid filename characters are replaced with underscores
