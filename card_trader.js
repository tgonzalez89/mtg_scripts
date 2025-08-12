select_elements = document.querySelectorAll('select[name="language"]')
select_elements.forEach(select => {
  const option = select.querySelector('option[value="en"]');
  if (option) {
    option.selected = true;
  }
})

select_elements = document.querySelectorAll('select[name="condition"]')
select_elements.forEach(select => {
  const option = select.querySelector('option[value="Moderately Played"]');
  if (option) {
    option.selected = true;
  }
})

select_elements = document.querySelectorAll('select[name="foil"]')
select_elements.forEach(select => {
  const option = select.querySelector('option[value=""]');
  if (option) {
    option.selected = true;
  }
})

select_elements = document.querySelectorAll('select[name="expansion"]')
select_elements.forEach(select => {
  const option = select.querySelector('option[value=""]');
  if (option) {
    option.selected = true;
  }
})


////////////////////////////////////////////////////////////////////////////////

////////// USE THIS ONE //////////

function changeSelectOptions(selectName, optionValue) {
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

changeSelectOptions('expansion', '');
changeSelectOptions('language', 'en');
changeSelectOptions('condition', 'Played');
changeSelectOptions('foil', '');
console.info("Done changeSelectOptions");


// function selectAndRelease(selectName) {
  // selectElements = document.querySelectorAll(`select[name="${selectName}"]`);
  // selectElements.forEach(select => {
    // select.dispatchEvent(new Event('change', { bubbles: true }));
    // select.dispatchEvent(new Event('click', { bubbles: true }));
  // });
// }
// selectAndRelease('language');
// selectAndRelease'condition');
// selectAndRelease('foil');
// selectAndRelease('expansion');
// console.info("Done selectAndRelease");


////////////////////////////////////////////////////////////////////////////////


select_name = 'language'
option_value = 'en'
select_elements = document.querySelectorAll(`select[name="${select_name}"]`);
select_elements.forEach(select => {
  const option = select.querySelector(`option[value="${option_value}"]`);
  if (option) {
    select.dispatchEvent(new Event('click', { bubbles: true }));
    option.selected = true;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    option.dispatchEvent(new Event('click', { bubbles: true }));
  } else {
    console.error(`Option with value="${option_value}" not found in select element with name="${select_name}".`);
  }
});

select_name = 'condition'
option_value = 'Moderately Played'
select_elements = document.querySelectorAll(`select[name="${select_name}"]`);
select_elements.forEach(select => {
  const option = select.querySelector(`option[value="${option_value}"]`);
  if (option) {
    select.dispatchEvent(new Event('click', { bubbles: true }));
    option.selected = true;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    option.dispatchEvent(new Event('click', { bubbles: true }));
  } else {
    console.error(`Option with value="${option_value}" not found in select element with name="${select_name}".`);
  }
});

select_name = 'expansion'
option_value = ''
select_elements = document.querySelectorAll(`select[name="${select_name}"]`);
select_elements.forEach(select => {
  const option = select.querySelector(`option[value="${option_value}"]`);
  if (option) {
    select.dispatchEvent(new Event('click', { bubbles: true }));
    option.selected = true;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    option.dispatchEvent(new Event('click', { bubbles: true }));
  } else {
    console.error(`Option with value="${option_value}" not found in select element with name="${select_name}".`);
  }
});

select_name = 'foil'
option_value = ''
select_elements = document.querySelectorAll(`select[name="${select_name}"]`);
select_elements.forEach(select => {
  const option = select.querySelector(`option[value="${option_value}"]`);
  if (option) {
    select.dispatchEvent(new Event('click', { bubbles: true }));
    option.selected = true;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    option.dispatchEvent(new Event('click', { bubbles: true }));
  } else {
    console.error(`Option with value="${option_value}" not found in select element with name="${select_name}".`);
  }
});
