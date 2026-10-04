#!/bin/sh
#
# Builds spectrum_demo.jpg: a single JPEG carrying embedded XMP mwg-rs
# (MWG Regions) metadata that exercises every code path in
# PhotoTaggingGramplet.get_xmp_regions(), for demoing/testing the
# "XMP Region Name" feature. See XMP_Region_Name.md, section 9.4.
#
# Requires: curl, exiftool (Image::ExifTool), ImageMagick (convert).
#
# Base photo: images/photo.6.embedded.jpg from
# https://github.com/skatsubo/exif-orientation-vs-face-regions
# (public-domain photo of Marie & Pierre Curie, originally contributed
# to immich-app/test-assets, carrying two genuine embedded MWG face
# regions used as-is for regions 1-2 below).
#
# What this script does:
#   1. Downloads the base photo (EXIF Orientation 6 / rotate-90-CW,
#      two named face regions).
#   2. Physically rotates it upright and resets Orientation to 1, so
#      the demo file has no orientation ambiguity of its own; region
#      coordinates for the two real faces are re-derived for the
#      rotated frame (see comments below).
#   3. Replaces the region metadata with a hand-built RDF/XML mwg-rs
#      block covering:
#        1. Marie Curie   (Face)  - normal region, re-derived coords
#        2. Pierre Curie  (Face)  - normal region, re-derived coords
#        3. Ada Lovelace  (Face)  - a third normal region (multi-person)
#        4. Laika         (Pet)   - non-"Face" Type, still named
#        5. Edge Case Left  (Face) - center near left edge; box would
#           extend past x=0, exercising the gramplet's clamp-to-[0,100]
#        6. Edge Case Right (Face) - same, clamped at the right edge
#        7. Malformed Data  (Face) - stArea:x is the non-numeric string
#           "garbage", which float() cannot parse, exercising the
#           ValueError fallback to a full-image (0,0,100,100) box
#
# Regenerating: run this script from an empty working directory.

set -e

BASE_URL="https://raw.githubusercontent.com/skatsubo/exif-orientation-vs-face-regions/main/images/photo.6.embedded.jpg"

curl -sL -o base.jpg "$BASE_URL"

# Physically rotate 90 deg CW to upright and reset Orientation to 1.
# Original stored (unrotated) size is 700x840; after rotation it's
# 840x700. A 90-deg-CW rotation maps a normalized center/size region
# (x, y, w, h) in the old frame to the new frame as:
#   x' = 1 - y     y' = x
#   w' = h         h' = w
# which is how the Marie/Pierre Curie coordinates below were derived
# from the originals (0.307857, 0.631548, 0.198571, 0.113095) and
# (0.239286, 0.3125, 0.241429, 0.0964286) respectively.
convert base.jpg -auto-orient upright.jpg

# Extract a template XMP packet -- still carrying the base photo's
# original (stale, pre-rotation) mwg-rs:Regions block, which is what
# gives the splice below something to find and replace.
exiftool -xmp -b upright.jpg > packet.xml
cp upright.jpg spectrum_demo.jpg

cat > new_regions_block.xml << 'BLOCK'
 <rdf:Description rdf:about=''
  xmlns:mwg-rs='http://www.metadataworkinggroup.com/schemas/regions/'
  xmlns:stArea='http://ns.adobe.com/xmp/sType/Area#'
  xmlns:stDim='http://ns.adobe.com/xap/1.0/sType/Dimensions#'>
  <mwg-rs:Regions rdf:parseType='Resource'>
   <mwg-rs:AppliedToDimensions rdf:parseType='Resource'>
    <stDim:w>840</stDim:w>
    <stDim:h>700</stDim:h>
    <stDim:unit>pixel</stDim:unit>
   </mwg-rs:AppliedToDimensions>
   <mwg-rs:RegionList>
    <rdf:Bag>
     <rdf:li rdf:parseType='Resource'>
      <mwg-rs:Area rdf:parseType='Resource'>
       <stArea:x>0.368452</stArea:x>
       <stArea:y>0.307857</stArea:y>
       <stArea:w>0.113095</stArea:w>
       <stArea:h>0.198571</stArea:h>
       <stArea:unit>normalized</stArea:unit>
      </mwg-rs:Area>
      <mwg-rs:Name>Marie Curie</mwg-rs:Name>
      <mwg-rs:Type>Face</mwg-rs:Type>
     </rdf:li>
     <rdf:li rdf:parseType='Resource'>
      <mwg-rs:Area rdf:parseType='Resource'>
       <stArea:x>0.687500</stArea:x>
       <stArea:y>0.239286</stArea:y>
       <stArea:w>0.096429</stArea:w>
       <stArea:h>0.241429</stArea:h>
       <stArea:unit>normalized</stArea:unit>
      </mwg-rs:Area>
      <mwg-rs:Name>Pierre Curie</mwg-rs:Name>
      <mwg-rs:Type>Face</mwg-rs:Type>
     </rdf:li>
     <rdf:li rdf:parseType='Resource'>
      <mwg-rs:Area rdf:parseType='Resource'>
       <stArea:x>0.500000</stArea:x>
       <stArea:y>0.060000</stArea:y>
       <stArea:w>0.080000</stArea:w>
       <stArea:h>0.080000</stArea:h>
       <stArea:unit>normalized</stArea:unit>
      </mwg-rs:Area>
      <mwg-rs:Name>Ada Lovelace</mwg-rs:Name>
      <mwg-rs:Type>Face</mwg-rs:Type>
     </rdf:li>
     <rdf:li rdf:parseType='Resource'>
      <mwg-rs:Area rdf:parseType='Resource'>
       <stArea:x>0.900000</stArea:x>
       <stArea:y>0.920000</stArea:y>
       <stArea:w>0.140000</stArea:w>
       <stArea:h>0.140000</stArea:h>
       <stArea:unit>normalized</stArea:unit>
      </mwg-rs:Area>
      <mwg-rs:Name>Laika</mwg-rs:Name>
      <mwg-rs:Type>Pet</mwg-rs:Type>
     </rdf:li>
     <rdf:li rdf:parseType='Resource'>
      <mwg-rs:Area rdf:parseType='Resource'>
       <stArea:x>0.020000</stArea:x>
       <stArea:y>0.500000</stArea:y>
       <stArea:w>0.300000</stArea:w>
       <stArea:h>0.200000</stArea:h>
       <stArea:unit>normalized</stArea:unit>
      </mwg-rs:Area>
      <mwg-rs:Name>Edge Case Left</mwg-rs:Name>
      <mwg-rs:Type>Face</mwg-rs:Type>
     </rdf:li>
     <rdf:li rdf:parseType='Resource'>
      <mwg-rs:Area rdf:parseType='Resource'>
       <stArea:x>0.980000</stArea:x>
       <stArea:y>0.500000</stArea:y>
       <stArea:w>0.300000</stArea:w>
       <stArea:h>0.200000</stArea:h>
       <stArea:unit>normalized</stArea:unit>
      </mwg-rs:Area>
      <mwg-rs:Name>Edge Case Right</mwg-rs:Name>
      <mwg-rs:Type>Face</mwg-rs:Type>
     </rdf:li>
     <rdf:li rdf:parseType='Resource'>
      <mwg-rs:Area rdf:parseType='Resource'>
       <stArea:x>garbage</stArea:x>
       <stArea:y>0.500000</stArea:y>
       <stArea:w>0.100000</stArea:w>
       <stArea:h>0.100000</stArea:h>
       <stArea:unit>normalized</stArea:unit>
      </mwg-rs:Area>
      <mwg-rs:Name>Malformed Data</mwg-rs:Name>
      <mwg-rs:Type>Face</mwg-rs:Type>
     </rdf:li>
    </rdf:Bag>
   </mwg-rs:RegionList>
  </mwg-rs:Regions>
 </rdf:Description>
BLOCK

python3 - << 'PYEOF'
with open("packet.xml", encoding="utf-8") as f:
    packet = f.read()
with open("new_regions_block.xml", encoding="utf-8") as f:
    new_block = f.read()

start_marker = " <rdf:Description rdf:about=''\n  xmlns:mwg-rs="
end_marker = " </rdf:Description>\n</rdf:RDF>"
start = packet.index(start_marker)
end = packet.index(end_marker, start) + len(" </rdf:Description>")
new_packet = packet[:start] + new_block.rstrip("\n") + packet[end:]

with open("packet_new.xml", "w", encoding="utf-8") as f:
    f.write(new_packet)
PYEOF

exiftool "-xmp<=packet_new.xml" -overwrite_original spectrum_demo.jpg

echo "Done: spectrum_demo.jpg"
exiftool -struct -j -G1 -RegionInfo spectrum_demo.jpg
