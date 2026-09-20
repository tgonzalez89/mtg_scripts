#!/usr/bin/env bash

set -euo pipefail

themes=(
  "all"
  "basic-types"
  "untapped"
)

budgets=(
  "ultra-low"
  "very-low"
  "low"
  "medium"
  "high"
  "very-high"
  "ultra-high"
  "extreme"
  "ultra-extreme"
  "unlimited"
)

budget_values=(10 20 30 50 100 200 500 1000 10000 100000)
max_price_values=(1 2 3 5 10 20 50 100 1000 10000)

for theme in "${themes[@]}"; do
  for i in "${!budgets[@]}"; do
    budget_name="${budgets[$i]}"
    budget="${budget_values[$i]}"
    max_price="${max_price_values[$i]}"

    filename="${theme}_${i}_${budget_name}.sh"

    case "$theme" in
      all)
        groups=(
          "otag:cycle-fetchland"
          "otag:cycle-abu-dual-land"
          "otag:tricycle-land"
          "otag:cycle-shockland"
          "otag:cycle-dual-surveil-land"
          "otag:cycle-bondland"
          "otag:cycle-triple-tapland"
          "otag:cycle-painland"
          "otag:cycle-soc-turbulent-land"
          "otag:cycle-slowland"
          "otag:cycle-fastland"
          "otag:cycle-verge"
          "otag:cycle-msh-basic-dual"
          "otag:cycle-tor-tainted-land"
          "otag:cycle-checkland"
          "otag:cycle-tangoland"
          "otag:cycle-reveal-land"
          "otag:cycle-pathway"
          "otag:cycle-horizon-land"
          "otag:cycle-hybrid-filterland"
          "otag:cycle-ody-filterland"
          "otag:cycle-bicycle-land"
          "otag:cycle-mh3-mdfc-dual-land"
          "otag:cycle-scry-land"
          "otag:cycle-mh3-landscape"
          "otag:cycle-snc-fetchland"
          "otag:cycle-ala-panorama"
          "otag:cycle-rav-bounceland"
          'is:mdfc t:land (t:instant or t:sorcery or t:enchantment or t:creature or t:artifact) o:"may pay 3 life"'
        )
        lands=(
          "Command Tower"
          "Exotic Orchard"
          "Fabled Passage"
          "Prismatic Vista"
          "Reflecting Pool"
          "Mana Confluence"
          "City of Brass"
          "Multiversal Passage"
        )
        ;;
      basic-types)
        groups=(
          "otag:cycle-fetchland"
          "otag:cycle-abu-dual-land"
          "otag:tricycle-land"
          "otag:cycle-shockland"
          "otag:cycle-dual-surveil-land"
          "otag:cycle-soc-turbulent-land"
          "otag:cycle-verge"
          "otag:cycle-msh-basic-dual"
          "otag:cycle-tor-tainted-land"
          "otag:cycle-checkland"
          "otag:cycle-tangoland"
          "otag:cycle-reveal-land"
          "otag:cycle-bicycle-land"
        )
        lands=(
          "Command Tower"
          "Fabled Passage"
          "Prismatic Vista"
          "Multiversal Passage"
        )
        ;;
      untapped)
        groups=(
          "otag:cycle-fetchland"
          "otag:cycle-abu-dual-land"
          "otag:cycle-shockland"
          "otag:cycle-bondland"
          "otag:cycle-painland"
          "otag:cycle-msh-basic-dual"
          "otag:cycle-tor-tainted-land"
          "otag:cycle-reveal-land"
          "otag:cycle-pathway"
          "otag:cycle-horizon-land"
          "otag:cycle-hybrid-filterland"
          "otag:cycle-ody-filterland"
        )
        lands=(
          "Command Tower"
          "Exotic Orchard"
          "Prismatic Vista"
          "Reflecting Pool"
          "Mana Confluence"
          "City of Brass"
          "Multiversal Passage"
        )
        ;;
    esac

    {
      echo '#!/usr/bin/env bash'
      echo
      echo 'python mana_base_creator.py \'
      echo '  --colors WUBRG \'
      echo '  --total_lands 40 \'
      echo '  --min_basics 5 \'
      echo "  --budget $budget \\"
      echo "  --max_price_group_average $max_price \\"
      echo "  --max_price_specific_lands $max_price \\"
      echo '  --price_source usd \'

      echo '  --enable_groups \'
      for group in "${groups[@]}"; do
        echo "    \"$group\" \\"
      done

      echo '  --enable_specific_lands \'
      for ((j = 0; j < ${#lands[@]}; ++j)); do
        if ((j == ${#lands[@]} - 1)); then
          echo "    \"${lands[$j]}\""
        else
          echo "    \"${lands[$j]}\" \\"
        fi
      done
    } >"$filename"

    chmod +x "$filename"
  done
done
