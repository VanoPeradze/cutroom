# Caption-render test font

DejaVu Sans 2.37, unmodified, from the official DejaVu release:
https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37

Archive: `dejavu-sans-ttf-2.37.zip`
SHA-256: `5c6e497a2f36552cb5ffb112c413a6af39c0f3c47653662b90b4fa6499822fd7`

Font SHA-256: `7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954`

The complete upstream license is included in `DejaVu-LICENSE.txt`.
The Bitstream Vera license permits redistributing this unmodified font; DejaVu changes are public domain.
This fixture is test-only. It is passed explicitly to libass via `fontsdir`,
not installed into the operating system and not used to change the product font.
No network, font download or installed fontconfig CLI is needed to run the tests.

Bold is also bundled so the all-style oracle does not select a different installed
bold face or synthesize one differently across platforms:
- Official archive `dejavu-fonts-ttf-2.37.zip`
- Archive SHA-256: `7576310b219e04159d35ff61dd4a4ec4cdba4f35c00e002a136f00e96a908b0a`
- `DejaVuSans-Bold.ttf` SHA-256: `e6476c1b80502924294eed40894c5b18e06c181444ca953e5334262df9c27724`
