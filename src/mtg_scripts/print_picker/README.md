Provides a Tkinter GUI for browsing card printings and exporting selected card lists or images.

Card requests and images are cached under the per-user `mtg-scripts` cache directory, in provider-specific `scryfall` or `riftcodex` namespaces. Set `MTG_SCRIPTS_CACHE_DIR` to choose a shared root or pass `--cache-dir PATH` to this command; the command-line path wins. The default is managed by `platformdirs` and is not created merely by importing the application.

The request-cache action clears JSON request entries only; the image-cache action clears image bytes only. Neither removes the bulk card database. The backend exposes a separate `refresh_database()` operation, which downloads/publishes a new version when Scryfall provides one and keeps the current reader's database open until backend shutdown. Failed refreshes use the newest schema-valid cached generation with a warning. Previous database generations and source-local legacy caches are retained; no automatic old-database cleanup is performed.

On first use, a valid local schema-v8 database may be copied from the previous package-local cache. Schema-v5/v6/v7 databases remain untouched but are not reused; a v8 build is required. The compact v8 database stores only fields used by the scripts, not complete Scryfall card JSON. Legacy JSON requests are imported as stale and refreshed; existing URL-addressed image files are imported lazily. If no compatible database exists, Scryfall's compressed bulk files may need to be downloaded and built locally. Keep sufficient disk space for the initial database and retained generations.

The application owns one `ScryfallService` and injects it into each Scryfall backend; closing a backend does not close a borrowed service. Shutdown stops UI callbacks and waits for active resolve/image workers before closing the backend and service. The adapter retains import parsing, flavor/direct-name ranking, foil choice, and playable-print preference. The service indexes optional oracle tags by oracle ID and can return every printing for a tag. Older bulk metadata without `oracle_tags` still builds a card database but reports tag lookup unavailable. General Scryfall query syntax remains API-backed rather than being approximated locally.

`exports.py` contains headless helpers for list aggregation, Windows-safe image naming, download path planning, and
unique-copy pixel encoding. Tk dialogs, backend image loading, and saving remain in `App`.

When downloading images, you can optionally make repeated copies distinct by changing a few pixel values. This makes exact pixel and file hashes differ; tools that use perceptual image matching may still treat the images as duplicates.
