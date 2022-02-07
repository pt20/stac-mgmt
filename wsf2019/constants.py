import pystac
from pystac.extensions.eo import Band

WSF2019_ID = "DLR-WSF2019"
WSF2019_TITLE = "WSF2019: world settlement footprint 2019"
WSF2019_DESCRIPTION = "DLR stuff"

WSF2019_LICENSE = "PDDL-1.0"

DLR_PROVIDER = pystac.Provider(
    name="German Aerospace Agency, DLR",
    url="https://download.geoservice.dlr.de/WSF2019/files/",
    roles=["producer", "licensor"],
)

WSF2019_BANDS = [
    Band.create(
        name="Settlement",
        description="Binary mask representing settlement",
    ),
]
