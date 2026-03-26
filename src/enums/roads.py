
from enum import Enum

class RoadType(str, Enum):
    highway = "highway"
    local = "local"
    gravel = "gravel"
    earthen = "earthen"

class RoadCategory(str, Enum):
    primary = "primary"
    secondary = "secondary"
    tertiary = "tertiary"

class RoadClass(str, Enum):
    national = "A"
    provincial = "B"
    municipal = "C"
    rural = "D"

class RoadLane(str, Enum):
    single = "single"
    double = "double"
    multi = "multi"

class RoadDirection(str, Enum):
    north = "north"
    south = "south"
    east = "east"
    west = "west"