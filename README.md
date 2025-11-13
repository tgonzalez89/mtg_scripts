# MTG helper scripts

Scripts to help automate various tasks related to Magic: The Gathering.



## Prerequisites

Python 3 (a recent version).

### Install required Python packages

```
pip install requirements.txt
```

If you open the requirements.txt you'll see which scripts need which packages.
If you don't want to install all of them just pick and choose which ones you want.

**Note:**
The `tesserocr` dependency can be tricky to install. Follow the instructions at https://pypi.org/project/tesserocr/ to install it for your platform.

## How to run

Run them using Python:
```
python <script_path> [args...]
```

To know about the specific arguments and options each script needs, just run:
```
python <script_path> --help
```



## Build Base Deck

Useful to generate an initial card list to create a new Commander deck. Pulls data from EDHREC and finds the most popular cards and generates a card list with the most included/most synergistic cards. You can import this file into your favorite deck building tool to start building your deck.

**Note:** This script checks both the 'average' and the 'budget' lists of cards.
I did it this way because I focus on building budget decks.
You can remove the budget parts if needed or change them to use the 'expensive' lists of cards instead.

### Inputs

* **Commander**<br>
  Name of the commander. Must match exactly.<br>
  If partners, the names must be separated by a space. Partners order matter. EDHREC is peculiar about this.<br>
  You can give multiple of them and the script will merge their data. Useful for commanders that play in the same way (like Ruby, Daring Tracker and Radha, Heir to Keld).<br>

* **Themes**<br>
  Pulls the lists of cards for these themes. If not given, doesn't filter by theme.

* **Synergy threshold**<br>
  Only cards that have EDHREC's synergy value above this threshold are taken into account.<br>
  Must be between 0 and 1 (15% would be 0.15, for example).<br>

* **Inclusion threshold**<br>
  Only cards that have a deck inclusion above this threshold are taken into account.<br>
  Must be between 0 and 1 (15% would be 0.15, for example).<br>

* **Price threshold**<br>
  Only cards below this threshold are taken into account.<br>
  Must be more than 0.<br>

* **Vendor**<br>
  Vendor to use to get the cards prices. Uses Card Kingdom by default.<br>

### Outputs
* **Card list**<br>
  File with the selected cards for your deck.
  Contains two sections:<br>
  * Main deck: Most included and most synergistic cards. Cards that you should most probably include in your deck.<br>
  * Considering: Other cards that match the provided filters but that are not as popular. Consider them for your deck.<br>

### TO DO

* Be flexible on the variants of budgets. Accept one or more of [average/default/normal], budget and expensive.



## Calculate To Purchase

Calculate which cards you need to purchase to build one or more new decks.<br>
This script compares your owned and purchased cards against the cards required by your target decks, taking into account which cards are already used in decks you currently own. It then generates lists of cards that you still need to buy.

### Inputs

* **Collection file**<br>
  Path to the file containing your the cards you own.<br>
  Export this file from [Moxfield collection](https://moxfield.com/collection) by going to **More → Export CSV**.<br>

* **Purchased file**<br>
  Path to the file listing cards you’ve already purchased but haven't received yet (effectively an extension of the collection file).<br>
  You can populate it by copy-pasting your list of cards from [CardTrader's orders](https://www.cardtrader.com/orders/buyer_future_order).<br>

* **Want deck IDs**<br>
  Moxfield deck IDs for the decks you want to build.<br>
  You can group variant decks using parentheses, e.g. `(deckID1,deckID2)`.<br>

* **Have deck IDs**<br>
  Moxfield deck IDs for the decks you already have built.<br>
  You can also group variants.<br>

* **Buy considering**<br>
  Whether to include cards in the "considering" pile when calculating which cards to buy.<br>

### Outputs

The script produces up to three text files, depending on your configuration:

* **To Purchase file**<br>
  Contains all cards you need to buy across your wanted decks.<br>

* **To Purchase Decks file**<br>
  Contains only the cards required specifically for your decks (excluding "considering" cards).

* **To Purchase Considering file**<br>
  Contains the list of "considering" cards you don’t yet own or have purchased.

Each file lists cards in the format:<br>
`<amount> <card_name>`



## CardMarket Optimizer

Work in progress.



## CardTrader Optimizer

CardTrader’s built-in optimizer only allows you to optimize for one language at a time.
This script automates the process of running the optimizer multiple times, once per selected language, and then compares results to find the cheapest option across all language.

**Note:** Make sure Firefox is completely closed before running this script.
The script reuses your Firefox profile to stay logged in to CardTrader.

### Firefox Profile Setup

The script requires access to your Firefox profile folder to reuse your existing login session.

Steps to locate it:
1. Open Firefox.
2. In the address bar, type: `about:profiles` and press **Enter**.
3. Find the profile you actively use — it’s usually labeled **“Default”**.
4. Under that profile, locate the **Root Directory** path.
5. Copy that path and provide it to the script via the `--browser-profile` argument.

Example:
```
C:\Users\<user>\AppData\Roaming\Mozilla\Firefox\Profiles\<random_string>.default-release
```

**Note:** In some cases reusing a profile can cause a bug where Firefox logs out of your Firefox account and can't login again. To avoid this, just copy-paste the profile and use the copy.

### Inputs

* **Card list**<br>
  Path to a text file containing the list of cards you want to optimize.<br>
  Each line should contain a single card name.<br>

* **Expansion choice**<br>
  Limits optimization to a specific expansion.<br>
  Use `"Any"` (default) to include all expansions.<br>

* **Foil choice**<br>
  Whether to consider foils when optimizing prices.<br>
  Options: `"Any"`, `"Yes"`, or `"No"` (default: `"Any"`).<br>

* **Condition**<br>
  Filters cards by condition.<br>
  Options: `"Any"`, `"Near Mint"`, `"Slightly Played"`, `"Moderately Played"`, `"Played"`, `"Poor"` (default: `"Any"`).<br>

* **Language price deltas**<br>
  Defines which languages to optimize and how much price difference you’re willing to tolerate per language.<br>
  Format: `'lang:delta,lang:delta,...'`<br>
  Example:
  ```
  en:0,es:25,pt:50
  ```
  In this case, English cards are prioritized, but Spanish cards up to 25 cents less English and Portuguese up to 50 cents less than Spanish will still be considered acceptable.<br>
  **Rules**
  * The first language must have a delta of `0`.
  * Deltas must be integers (in cents).
  * `"Any"` may only appear as the **last** language.
  * Allowed languages: `Any, de, en, es, ft, it, jp, kr, pt, ru, zh-CN, zh-TW`<br>

* **Browser profile**<br>
  Path to your Firefox profile directory.<br>
  Required to use your CardTrader login session.<br>
  See the [Firefox Profile Setup](#firefox-profile-setup) section above.<br>

### What it does

* Opens CardTrader in Firefox using your profile.
* Iterates through the specified languages and runs CardTrader’s built-in optimizer for each.
* Applies your chosen filters (expansion, foil, condition).
* Collects prices and determines the cheapest configuration across all languages.
* Automates all browser interaction, no manual input required once started.
* Runs a final round of CardTrader’s built-in optimizer with the selected language per card.

### TO DO

* Accept other browser profiles (Chrome, Edge, etc.).



## Forge Auto Battler

This script automates Forge Adventure matches between multiple decks. It runs repeated 4-player free-for-all simulations, cycling through all possible combinations of decks, and reports their win rates once the simulations complete.

Forge includes a mode that allows automated play between AI-controlled decks. This script controls that process so you can efficiently evaluate deck performance over many simulated games without manual intervention.

### Setup and Requirements

#### Forge
Download and install Forge from: https://github.com/Card-Forge/forge

Use the **Forge Adventure** interface, not the standard one. This mode provides the appropriate layout and behavior for bot matches.
Make sure Forge is running in windowed mode and set to 1080p resolution for proper automation and screen recognition.

#### Tesseract OCR
This script uses [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) for visual data extraction during simulation.
Installation can be tricky, follow the detailed instructions from the [tesserocr documentation](https://pypi.org/project/tesserocr/).

For Windows users, the easiest way is to download a precompiled wheel from [https://github.com/simonflueckiger/tesserocr-windows_build/releases](https://github.com/simonflueckiger/tesserocr-windows_build/releases), and then install it with:
```
pip install <path_to_wheel_file>
```

#### Tesseract Data Path
Inside the script, update the `tesser_data` variable to point to your local Tesseract `tessdata` directory.

For example:
```
tesser_data = r"C:\Program Files\Tesseract-OCR\tessdata"
```

You can download the data from here: https://github.com/tesseract-ocr/tessdata.
English language is the only one you need ([eng.traineddata](https://github.com/tesseract-ocr/tessdata/blob/main/eng.traineddata)).

### Inputs

* **Decks**<br>
  List of deck names to include in the simulations. You must provide at least 4 decks.<br>
  The decks must already exists in Forge and their names must match exactly the ones in this list.<br>

* **Minimum matches**<br>
  Minimum number of matches to run before stopping.<br>
  Useful for low deck counts where the combinations are few.<br>

### What it does

* Launches Forge Adventure mode.
* Loads the specified decks and organizes all possible 4-player combinations.
* Runs simulated matches between AI players until the minimum match threshold is reached (if specified).
* Tracks results and computes win rates for each deck.
* Displays final win rate statistics when finished.

### TO DO

* Make the simulation framework support a flexible number of players (2–4, possibly more).
* Be flexible on the format. Right now only Commander is supported.
* Provide detailed setup instructions on how to setup Forge and instruction how to get it to the point where the script can run. Also maybe automate the whole process, making the script launch Forge by itself.



## Other Scripts

### Count Occurences

Open a list of files and count how many times each line appears across all files.

```
count_occurrences.py FILE [FILE ...]
```

### Filter List

Given two files, returns the lines in the first one that do not appear in the second one.

```
filter_list.py FILE1 FILE2
```
