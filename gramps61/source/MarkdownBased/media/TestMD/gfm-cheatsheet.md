# What's Up With Markdown

* [TestFile.md](../TestFile.md) • [gfm-test.md](gfm-test.md) • [gfm-cheatsheet.md](gfm-cheatsheet.md)
## _GitHub Flavored Markdown Cheat Sheet_

This serves as a quick reference and showcase of GitHub Flavored Markdown. For more complete info, see [John Gruber's original spec](http://daringfireball.net/projects/markdown/) and the [Github-flavored Markdown info page](http://github.github.com/github-flavored-markdown/). 



# Table of Contents  

  
[Blockquotes](#blockquotes)   
[Code and Syntax Highlighting](#code-and-syntax-highlighting)  
[Emphasis](#emphasis)  
[Headers](#headers)  
[Horizontal Rule](#horizontal-rule)  
[HTML in Markdown](#html-in-markdown)  
&nbsp;&nbsp;&nbsp; [_SUP SUB & PRE_](#sup-sub-pre)     
&nbsp;&nbsp;&nbsp; [_HTML Tables_](#html-tables)     
&nbsp;&nbsp;&nbsp; [_Details/Summary_](#detailssummary)     
[Images](#images)  
[Links](#links)  
[Lists](#lists)  
[_NEW!_ Mathematics](#mathematics)     
[Notes](notes)  
[New Line/Line Breaks](#line-breaks)  
[Tables](#tables)  

-----


-----
## Blockquotes

```markdown
>> Blockquotes are very handy in email to emulate reply text.
>> This line is part of the same quote.
>  
> This is one less quote level
This line gets incorporated with the quote because it's only a single newline away

Quote break.

> This is a very long line that will still be quoted properly when it wraps. Oh boy let's keep writing to make sure this is long enough to actually wrap for everyone. Oh, you can *put* **Markdown** into a blockquote. 

```

>> Blockquotes are very handy in email to emulate reply text.
>> This line is part of the same quote.
>    
> This is one less quote level
This line gets incorporated with the quote because it's only a single newline away

Quote break.

> This is a very long line that will still be quoted properly when it wraps. Oh boy let's keep writing to make sure this is long enough to actually wrap for everyone. Oh, you can *put* **Markdown** into a blockquote. 

-----
## Code and Syntax Highlighting

Code blocks are part of the Markdown spec, but syntax highlighting isn't. However, many renderers -- like Github's and *Markdown Here* -- support syntax highlighting. *Markdown Here* supports highlighting for dozens of languages (and not-really-languages, like diffs and HTTP headers); to see the complete list, and how to write the language names, see the [highlight.js demo page](http://softwaremaniacs.org/media/soft/highlight/test.html).

```markdown
Inline `code` has `back-ticks around` it.
```

Inline `code` has `back-ticks around` it.


Blocks of code are either fenced by lines with three back-ticks <code>```</code>, or are indented with four spaces. I recommend only using the fenced code blocks -- they're easier and only they support syntax highlighting.

```markdown

      ```javascript
      var s = "JavaScript syntax highlighting";
      alert(s);
      ```

      ```python
      s = "Python syntax highlighting"
      print s
      ```

      ```
      No language indicated.
      let what = 'will it' + B;

      // let's throw in a comment
      <b>tag</b>.
      ```
          // And code blocks that are just indented 4 spaces
          let me = out > ofHere ? 'bye' : 'never' ;
          return null;
          me = 'help I'm trapped after the return line!';

```

```javascript
var s = "JavaScript syntax highlighting";
alert(s);
```

```python
s = "Python syntax highlighting"
print s
```

```
No language indicated.
let what = 'will it' + B;

// let's throw in a comment
<b>tag</b>.
```
    // And code blocks that are just indented 4 spaces
    let me = out > ofHere ? 'bye' : 'never' ;
    return null;
    me = 'help I'm trapped after the return line!';
    
    

Again, to see what languages are available for highlighting, and how to write those language names, see the [highlight.js demo page](http://softwaremaniacs.org/media/soft/highlight/test.html).

---
## Emphasis

```markdown
Emphasis, aka italics, with *asterisks* or _underscores_.

Strong emphasis, aka bold, with **asterisks** or __underscores__.

Combined emphasis with **asterisks and _underscores_**.

Strikethrough uses one tilde ~Scratch This~ or two tildes. ~~Scratch this.~~ 
```

Emphasis, aka italics, with *asterisks* or _underscores_.

Strong emphasis, aka bold, with **asterisks** or __underscores__.

Combined emphasis with **asterisks and _underscores_**.

Strikethrough uses one tilde ~Scratch This~ or two tildes. ~~Scratch this.~~ 

Note: In the GitHub text editor, only two tildes shows the inline preview, but    
either one or two tildes show the same on output.

-----
## Headers

```markdown
For H1 and H2, an underline-ish style:

Alt-H1
======

Alt-H2
------

Or the more common 

# H1
## H2
### H3
#### H4
##### H5
###### H6
```

For H1 and H2, an underline-ish style:

Alt-H1
======

Alt-H2
------

Or the more common 

# H1
## H2
### H3
#### H4
##### H5
###### H6

-----
## Horizontal Rule

```markdown
Three or more...

Hyphens

---

Asterisks

***

Underscores
___

All become a thick horizontal line.
```

Three or more...

Hyphens

---

Asterisks

***

Underscores
___

All become a thick horizontal line.

-----
## HTML in Markdown

You can also use raw HTML in your Markdown... sometimes:

```markdown
<dl>
  <dt>Definition list</dt>
  <dd>Is something people use sometimes.</dd>

  <dt>Markdown in HTML</dt>
  <dd>Does *not* work **very** well. Use HTML <em>tags</em>.</dd>
</dl>


For &lt;img&gt; see [***Images***](#images)  
```

<dl>
  <dt>Definition list</dt>
  <dd>Is something people use sometimes.</dd>

  <dt>Markdown in HTML</dt>
  <dd>Does *not* work **very** well. Use HTML <em>tags</em>.</dd>
</dl>

For &lt;img&gt; see [***Images***](#images)  

### SUP SUB & PRE

```
SuperScript<sup>You *can* use **markdown** in ***superscript***</sup>

SubScript<sub>You *can* use **markdown** in ***subscript***</sub>

<pre>      The
       &lt;Pre&gt;
           Tag
    Works    similar    to    ```
But < and > are not escaped around a <word>
This allows <i>some</i> tags in <b>the pre</b> area<sup>Super!</sup></pre>
```
SuperScript<sup>You *can* use **markdown** in ***superscript***</sup>

SubScript<sub>You *can* use **markdown** in ***subscript***</sub>

<pre>      The
       &lt;Pre&gt;
           Tag
    Works    similar    to    ```
But < and > are not escaped around a <word>
This allows <i>some</i> tags in <b>the pre</b> area<sup>Super!</sup></pre>

### HTML Tables

```markdown
 <table>
  <tr><th>HTML</th><th>Tables</th><th colspan="2">Are Possible</th></tr>
  <tr><th colspan="2">Dessert:</th><td>Jello</td><td>Whirrled</td></tr>
  <tr><td colspan="4" align="center">And more flexible</td></tr>
  <tr><td colspan="4" align="center">since you can use colspan</td></tr>
  <tr><td>And</td><td rowspan="2" colspan="2" align="center">rowspan</td><td>To</td></tr>
  <tr><td>Also</td><td>Boot</td></tr>
 </table>
```

 <table>
  <tr><th>HTML</th><th>Tables</th><th colspan="2">Are Possible</th></tr>
  <tr><th colspan="2">Dessert:</th><td>Jello</td><td>Whirrled</td></tr>
  <tr><td colspan="4" align="center">And more flexible</td></tr>
  <tr><td colspan="4" align="center">since you can use colspan</td></tr>
  <tr><td>And</td><td rowspan="2" colspan="2" align="center">rowspan</td><td>To</td></tr>
  <tr><td>Also</td><td>Boot</td></tr>
 </table>

### Details/Summary
```markdown
But perhaps the most useful add is that of details/summary

<details><summary><b>Click here</b> for a surprise!</summary>

   
**I'm hidden till I'm not, then**
   
### Sir, Prize!
   
I can use markdown **here in details**, but no markdown in the **summary**.
   
   
</details>

```

But perhaps the most useful add is that of details/summary

<details><summary><b>Click here</b> for a surprise!</summary>

   
**I'm hidden till I'm not, then**
   
### Sir, Prize!
   
I can use markdown **here in details**, but no markdown in the **summary**.
   
   
</details>



-----
## Images

```markdown
Here's a logo (hover logo to see the alt text):

Inline-style: 
![don't forget to do alt text](https://avatars.githubusercontent.com/u/42009457?s=40&v=4 "Logo Title Hover Text")

Reference-style: 
![don't forget to do alt text, this is a logo][logo]

And regular HTML img tags work, and allows setting the width or height, and classes for use with pages:

<img width="200" alt="Hi There! Please be descriptive with Alt Text!!" class="recess" src="https://avatars.githubusercontent.com/u/42009457?s=400&u=2dcba5c146315f82f802b8b58e92a4d6b82344b3&v=4">

[logo]: https://avatars.githubusercontent.com/u/42009457?s=40&v=4 "Logo Title Hover Text: The Sequel"

```

Here's a logo (hover to see the title text):

Inline-style: 
![don't forget to do alt text](https://avatars.githubusercontent.com/u/42009457?s=40&v=4 "Logo Title Hover Text")

Reference-style: 
![don't forget to do alt text, this is a logo][logo]

And regular HTML img tags work, and allows setting the width or height, and classes for use with pages:

<img width="200" alt="Hi There! Please be descriptive with Alt Text!!" class="recess" src="https://avatars.githubusercontent.com/u/42009457?s=400&u=2dcba5c146315f82f802b8b58e92a4d6b82344b3&v=4">

[logo]: https://avatars.githubusercontent.com/u/42009457?s=40&v=4 "Logo Title Hover Text: The Sequel"





---
## Links

There are several ways to create links.

```markdown
[I'm an inline-style link](https://www.google.com)

[I'm a reference-style link][Arbitrary case-insensitive reference text]

[You can use numbers][1] for reference-style link definitions

Or leave it empty and use the [link text itself][]

This is useful when you are doing lots of cites [[2],[3]].

Some text to show that the reference links can follow later. 
But while we're at it, might as well point out we can use 
<a href="#Links" class="dismissed">html links</a> too—this is 
useful if you need to add a class for use with pages/Jeckyl/whatever.

The actual links for the above examples are below this line, but hidden in the final html output.

[arbitrary case-insensitive reference text]: https://git.myndex.com
[1]: http://apcacontrast.com
[link text itself]: http://tangledweb.xyz
[2]: http://apcacontrast.com
[3]: https://linktr.ee/Myndex

-----
*This space for lease*
```

[I'm an inline-style link](https://www.google.com)

[I'm a reference-style link][Arbitrary case-insensitive reference text]

[You can use numbers][1] for reference-style link definitions

Or leave it empty and use the [link text itself][]

This is useful when you are doing lots of cites [[2],[3]].


Some text to show that the reference links can follow later. 
But while we're at it, might as well point out we can use 
<a href="#Links" class="dismissed">html links</a> too—this is 
useful if you need to add a class for use with pages/Jeckyl/whatever.

The actual links for the above examples are below this line, but hidden in the final html output.

[arbitrary case-insensitive reference text]: https://git.myndex.com
[1]: http://apcacontrast.com
[link text itself]: http://tangledweb.xyz
[2]: http://bridgepca.com
[3]: https://linktr.ee/Myndex

-----
*This space for lease*

---
## Lists

```markdown
1. First ordered list item
2. Another item
    * Unordered sub-list, lead with 4 spaces
1. Actual numbers don't matter, just that it's a number
    1. Ordered sub-list, lead with 4 spaces
        1. More sub, lead with 4 spaces
            3. Notice how the numbers can get janky
            1. Notice how the numbers can get janky
        2. previous sub
    2. previous sub
4. And another item.


1. Main level
    1. second level
        1. third level
            - fourth level
        2. third level
    2. Second level
7. main level



Unordered list:

- This is a list
    - This is a sub list, lead with 4 spaces
        - and a further sublist, lead with 4 spaces
            - and still more subing
    - back down a few
    1. add in some ordered stuff
    3. more ordered stuff
        2. sub ordered stuff
            1. Hi There
- Back to the future
   
   Some text that should be aligned with the above item.

* Unordered list can use asterisks
- Or minuses
+ Or pluses
```

1. First ordered list item
2. Another item
    * Unordered sub-list, lead with 4 spaces
1. Actual numbers don't matter, just that it's a number
    1. Ordered sub-list, lead with 4 spaces
        1. More sub, lead with 4 spaces
            3. Notice how the numbers can get janky
        7. previous sub
    2. previous sub
4. And another item.


1. Main level
    1. second level
        1. third level
            - fourth level
        2. third level
    2. Second level
7. main level


Unordered list:

- This is a list
    - This is a sub list, lead with 4 spaces
        - and a further sublist, lead with 4 spaces
            - and still more subing
    - back down a few
    1. add in some ordered stuff
    3. more ordered stuff
        2. sub ordered stuff
            1. Hi There
- Back to the future
   
   Some text that should be aligned with the above item.

* Unordered list can use asterisks
- Or minuses
+ Or pluses


-----
## Line Breaks 

Here are some things to try out:

```markdown
Here's a line for us to start with.

This line is separated from the one above by two newlines, so it will be a *separate paragraph*.

This line is also begins a separate paragraph, but,
despite having a single newline, it just gets wrapped together.

This line ends with four white spaces before hitting return.    
So the next line becomes a single new line
```

Here's a line for us to start with.

This line is separated from the one above by two newlines, so it will be a *separate paragraph*.

This line is also begins a separate paragraph, but,
despite having a single newline, it just gets wrapped together.

This line ends with four white spaces before hitting return.    
So the next line becomes a single new line

-----
## Mathematics

GitHub Markdown can display LaTeX formulas using MathJax, either inline or as a code block.

```markdown

### Inline

This sentence uses `$` delimiters to show math inline: $\sqrt{3x-1}+(1+x)^2$

This sentence uses <span>$</span>\` and \`<span>$</span> delimiters to show math inline: $`\sqrt{3x-1}+(1+x)^2`$


### Blocks

**The Cauchy-Schwarz Inequality**\
$$\left( \sum_{k=1}^n a_k b_k \right)^2 \leq \left( \sum_{k=1}^n a_k^2 \right) \left( \sum_{k=1}^n b_k^2 \right)$$


      **The Cauchy-Schwarz Inequality**

      ```math
      \left( \sum_{k=1}^n a_k b_k \right)^2 \leq \left( \sum_{k=1}^n a_k^2 \right) \left( \sum_{k=1}^n b_k^2 \right)
      ```


### Escapes

This expression uses `\$` to display a dollar sign: $`\sqrt{\$4}`$

For a dollar sign in a sentence that has latex elsewhere, use <span>$</span> to distinguish from the $100/2$


```

### Inline

This sentence uses `$` delimiters to show math inline: $\sqrt{3x-1}+(1+x)^2$

This sentence uses <span>$</span>\` and \`<span>$</span> delimiters to show math inline: $`\sqrt{3x-1}+(1+x)^2`$


### Blocks
       
**The Cauchy-Schwarz Inequality**\
$$\left( \sum_{k=1}^n a_k b_k \right)^2 \leq \left( \sum_{k=1}^n a_k^2 \right) \left( \sum_{k=1}^n b_k^2 \right)$$

      
**The Cauchy-Schwarz Inequality**

```math
\left( \sum_{k=1}^n a_k b_k \right)^2 \leq \left( \sum_{k=1}^n a_k^2 \right) \left( \sum_{k=1}^n b_k^2 \right)
```

### Escapes

This expression uses `\$` to display a dollar sign: $`\sqrt{\$4}`$

For a dollar sign in a sentence that has latex elsewhere, use <span>$</span> to distinguish from the $100/2$


### See Also
More on MathJax: http://mathjax.org/

-----
## Notes

```markdown
> [!NOTE]  
> Highlights information that users should take into account, even when skimming.

> [!TIP]
> Optional information to help a user be more successful.

> [!IMPORTANT]  
> Crucial information necessary for users to succeed.

> [!WARNING]  
> Critical content demanding immediate user attention due to potential risks.

> [!CAUTION]
> Negative potential consequences of an action.
```

> [!NOTE]  
> Highlights information that users should take into account, even when skimming.

> [!TIP]
> Optional information to help a user be more successful.

> [!IMPORTANT]  
> Crucial information necessary for users to succeed.

> [!WARNING]  
> Critical content demanding immediate user attention due to potential risks.

> [!CAUTION]
> Negative potential consequences of an action.


-----
## Tables

```markdown
Colons can be used to align columns.

| Tables        | Are           | Cool  |
| ------------- |:-------------:| -----:|
| col 3 is      | right-aligned | $1600 |
| col 2 is      | centered      |   $12 |
| zebra stripes | are neat      |    $1 |

The outer pipes (|) are optional, and you don't need to make the raw Markdown line up prettily. You can also use inline Markdown.

Markdown | Less | Pretty
--- | --- | ---
*Still* | `renders` | **nicely**
1 | 2 | 3
```

Colons can be used to align columns.

| Tables        | Are           | Cool |
| ------------- |:-------------:| -----:|
| col 3 is      | right-aligned | $1600 |
| col 2 is      | centered      |   $12 |
| zebra stripes | are neat      |    $1 |

The outer pipes (|) are optional, and you don't need to make the raw Markdown line up prettily. You can also use inline Markdown.

Markdown | Less | Pretty
--- | --- | ---
*Still* | `renders` | **nicely**
1 | 2 | 3

> [!NOTE] 
> Also see HTML tables above in [HTML Tables](#html-tables)


-----

> [!TIP]
> Any requests for features fleshed out? DM me or leave a message below.

This cheatsheet started with a fork of Joshua Pekera's _"Markdown Here"_. This Gist is expanded to cover **GitHub Flavored Markdown**, and the nuances of working with various GitHub documents.

-----

Last updated July 25, 2026 (Added LaTeX math and fixed blockquotes)
