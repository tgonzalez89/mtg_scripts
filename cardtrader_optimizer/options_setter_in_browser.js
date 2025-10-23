// Open browser
// Go to https://www.cardtrader.com/wishlists/new and import the list of cards you want
// or go to your pre-made wishlist.
// Press F12 to bring up the developer tools
// Click on Console
// Copy-paste this code and press run, wait for the 'Done!' message (can take several seconds, maybe even a minute)
// Afterwards you can click the Optimize button to make Cardtrader calculate the order price

function setOptions(selectName, optionValue) {
  selectElements = document.querySelectorAll(`select[name="${selectName}"]`);
  selectElements.forEach(select => {
    const option = select.querySelector(`option[value="${optionValue}"]`);
    if (option) {
      select.value = optionValue;
      option.selected = true;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      option.dispatchEvent(new Event('click', { bubbles: true }));
    } else {
      console.error(`Option with value="${optionValue}" not found in select element with name="${selectName}".`);
    }
  });
}

console.info("Setting expansion");
setOptions('expansion', '');

console.info("Setting language");
setOptions('language', 'en');

console.info("Setting condition");
setOptions('condition', 'Played');

console.info("Setting foil");
setOptions('foil', '');

console.info("Done!");
