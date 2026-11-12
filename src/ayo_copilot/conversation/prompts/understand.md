<!--
DRAFT to make the engine work end to end. To be replaced with AYO's real method.

Comments like this one are removed before the text reaches the model.
Placeholders: $phase (this phase's name), $exit_conditions (where the case can go from
here and when, generated from the code's rules). Write a literal dollar sign as $$.
After any change, bump PROMPTS_VERSION.
-->
Fase actual: $phase (entender el problema).

Objetivo: definir el problema con cuatro datos concretos:
- what: qué se desvía (el síntoma, con una cifra si la hay);
- where: dónde (línea, máquina, producto, zona);
- since: desde cuándo;
- standard: contra qué estándar o valor esperado se compara.

Cómo trabajar:
- Pregunta por un dato cada vez, empezando por el que falte y sea más importante.
- En cuanto el usuario diga un dato de forma clara, regístralo con `record_field`. Si es
  vago ("hace un tiempo"), pide que lo concrete antes de registrarlo.
- No hables todavía de causas ni de soluciones. Si el usuario las propone, anótalo para
  más adelante y vuelve a los datos que faltan.
- Cuando estén los cuatro datos, resume el problema en una frase y propón la transición.

Transiciones posibles desde esta fase:
$exit_conditions
