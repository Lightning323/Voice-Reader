# Screenplay Reader
A python base UI for reading screenplays.

## Influencing reading tone and speed

A few characters or markers in the screenplay can be used to change the reading tone or speed.

### Speed
Adding an indicator in parentheses can change the reading speed of that line.

* To make the line read faster, use `(_f_)` `(fast)`, `(frantic)`, or `(quick)`.

* To make the line slower, ise `(_s_)` `(slow)`, `(methodical)`, or `(thorough)`.

* You can increase or decrease even further by adding "very" `(very fast)`, `(very slow)`, etc, or `(_ff_)`, `(_ss_)`.
    * `(_fff_)`, `(_sss_)` for increased speed, etc.

### Interruptions
Put a hyphen (`--` or `-`) at the end of a line to interrupt the line.

### Pauses
Put a "`. . .`" at the end of a line or on a newline to pause for a few seconds.