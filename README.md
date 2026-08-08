basic adapter for converting whatever openRGB
this requires com0com: https://sourceforge.net/projects/com0com/
which does also mean no secure boot (sorry ;(, maybe theyll add this to open RGB soon and this will be a cool relic)
regardless, the RGB controller is, obviously, rgb.py
and the screen controller is screen.py

the screen controller requires some work in openRGB, you can either leave it as one really long LED (1920!) or you can use visualmap and use zigzag to create a 32 tall block, this will create a VSERP? pattern (i need to check that)
https://openrgb.org/plugin_visual_map.html
might be HSERP, just do some testing.

good luck!
and as usual, if anything here is too complicated, @hermivore on discord
happy rgb-ing!
