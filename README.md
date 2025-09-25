# Introduction to Automated and Intelligent Systems Project

This project was made during pratical classes for Introduction to Automated and
Intelligent Systems class in the bachelor's in Artificial Intelligence and Data
Science.

## How to build

### Requirements
    - Docker
        - On Linux systems
        `sudo apt install docker` (Ubuntu and Debian)
        `sudo yay -S docker` (Arch)

### Running the container

To build and run:
`
./run.sh build
`

To run the container:
`
./run.sh up
`

To access the container shell:
`
./run.sh sh
`

To run virtualenv in the container shell:
`
./run.sh virtualenv
`

To stop the container:
`
./run.sh down
`

To remove the container:
`
./run.sh remove
`
