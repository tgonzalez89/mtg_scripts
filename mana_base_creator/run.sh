#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 6 ]]; then
    cat <<EOF
Usage:
    $0 <budget> <theme> <colors> <total_lands> <min_basics> <price_source> [extra options...]

Example:
    $0 medium all WUBRG 40 5 usd \
        --allow_off_color_lands \
        --disable_specific_lands "Command Tower" "Exotic Orchard"
EOF
    exit 1
fi

budget_name="$1"
theme="$2"
colors="$3"
total_lands="$4"
min_basics="$5"
price_source="$6"

shift 6

declare -A budgets=(
    [ultra-low]=10
    [very-low]=20
    [low]=30
    [medium]=50
    [high]=100
    [very-high]=200
    [ultra-high]=500
    [extreme]=1000
    [ultra-extreme]=10000
    [unlimited]=100000
)

declare -A max_prices=(
    [ultra-low]=1
    [very-low]=2
    [low]=3
    [medium]=5
    [high]=10
    [very-high]=20
    [ultra-high]=50
    [extreme]=100
    [ultra-extreme]=1000
    [unlimited]=10000
)

if [[ -z ${budgets[$budget_name]+x} ]]; then
    echo "Unknown budget: $budget_name"
    exit 1
fi

budget="${budgets[$budget_name]}"
max_price="${max_prices[$budget_name]}"

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
    mdfcs-all)
        groups=(
            "otag:cycle-mh3-mdfc-dual-land"
            'is:mdfc t:land (t:instant or t:sorcery or t:enchantment or t:creature or t:artifact) o:"may pay 3 life"'
            'is:mdfc t:land (t:instant or t:sorcery or t:enchantment or t:creature or t:artifact) o:"This land enters tapped."'
        )
        lands=()
        ;;
    mdfcs-dual-untapped)
        groups=(
            "otag:cycle-mh3-mdfc-dual-land"
            'is:mdfc t:land (t:instant or t:sorcery or t:enchantment or t:creature or t:artifact) o:"may pay 3 life"'
        )
        lands=()
        ;;
    *)
        echo "Unknown theme: $theme"
        exit 1
        ;;
esac

cmd=(
    python mana_base_creator.py
    --colors "$colors"
    --total_lands "$total_lands"
    --min_basics "$min_basics"
    --budget "$budget"
    --max_price_group_average "$max_price"
    --max_price_specific_lands "$max_price"
    --price_source "$price_source"
    --enable_groups "${groups[@]}"
    --enable_specific_lands "${lands[@]}"
    "$@"
)

echo "Running:"
printf ' %q' "${cmd[@]}"
echo
echo

exec "${cmd[@]}"
