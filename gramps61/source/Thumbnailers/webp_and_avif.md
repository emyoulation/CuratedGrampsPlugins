#  .webp and .avif format
[README.md](README.md) • [`.webp` and `.avif` format (native) support in the primary OSes](webp_and_avif.md)

> Does windows 10 natively support `.webp` and/or `.avif` image formats?

**Windows 10** does not support `.webp` or `.avif` formats completely out of the box without additional components. Native decoding for `.webp` requires installing the free WebP Image Extension from the Microsoft Store, while `.avif` requires the optional AV1 Video Extension or specific system codecs. 

## Windows 10 Support Status
### WebP Support Details

* **`webp` Format**: 
  * **File Explorer & Photos**: Out-of-the-box Windows 10 often fails to show thumbnails or open `.webp` files in the default Photos app until you install the official WebP Image Extension.
  * **Web Browsers**: Modern browsers running on Windows 10 (like Edge and Chrome) render `.webp` natively.

### AVIF Support Details
  * **System Codecs**: Windows 10 has partial, background-level hooks for AVIF depending on the exact OS build and installed video extensions, but it is not fully robust or seamless out-of-the-box like in Windows 11.
  * **Workarounds**: Installing the free AV1 Video Extension from the Microsoft Store helps unlock viewing capabilities in select native apps, though dragging files into a browser like Chrome or Edge remains a more reliable fallback.

There are free third-party image viewers or tools (like IrfanView or Paint.net) that open both formats on Windows 10 without needing individual Microsoft Store extensions. 

## macOS Support Status
macOS natively supports both formats, but compatibility depends entirely on your operating system version.

* **`webp` Format**: Fully supported since macOS Big Sur (11). You can view WebP images directly in Finder, Safari, and Preview without any modifications.
***`.avif` Format**: Fully supported since macOS Ventura (13). On Ventura or later, the OS handles AVIF files natively across Finder, Preview, and Quick Look.

## Linux Support Status
Linux distributions widely support both formats natively, though the exact behavior depends on your chosen Desktop Environment (like GNOME or KDE).
* **`.webp` Format**: Natively supported on nearly all mainstream Linux distributions (Ubuntu, Fedora, Arch, etc.). Default GNOME and KDE image viewers decode WebP files out of the box.
* **`.avif` Format**: Natively supported on most modern distributions released after 2021.
  * **GNOME/GTK Environments**: Supported natively since the release of libavif 0.8.0 via a system plugin.
  * **KDE/Qt Environments**: Supported natively through the KImageFormats library.
  * **Exception**: If you use a minimalist or older enterprise Linux distribution, you may need to manually install system codecs (like libavif-bin or webp-pixbuf-loader) via your package manager.
