#!/usr/bin/env bash
pip install code2logic --upgrade
pip install code2llm --upgrade

#code2logic ./ -f toon --compact --no-repeat-module --function-logic --with-schema --name project -o ./

code2logic ./ -f toon --compact --name project -o ./
#code2llm ./ -f toon
#code2llm ./ -f all
#code2llm ./ -f toon -o ./
code2llm ./ -f toon,evolution -o ./project