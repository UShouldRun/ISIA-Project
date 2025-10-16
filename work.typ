#set page(paper: "a4", margin: (x: 2cm, y: 1.5cm))
#set text(font: "New Computer Modern", size: 11pt)
#set par(justify: false, leading: 0.65em)

= SIA Workflow

== Agents Roles

- *Rover*:
  - *Liveness*: explore terrain, analyze soil samples, detect resources, pick up malfunctioned agents
  - *Safety*: battery power, mobility constraints, not colide with objects

- *Drone*:
  - *Liveness*: map areas quickly, identify points of interest, relay data to rovers
  - *Safety*: battery power, not collide with objects

- *Base Station*:
  - *Liveness*: store collected data, recharge rovers/drones, coordinate logistics
  - *Safety*: must not destroy drones or rovers

- *Mechanic*:
  - *Liveness*: assures drone, rover and other mechanic agents are working properly,
    as well as fix them

- *Sattelite*:
  - *Liveness*: decision making

== Communication Protocols

- Drone:
  - Sattelite: mission
  - Rover: immediate action
  - Drone: immediate action
  - Base: if sattelite not available

  - Drone & Rover: current position, potential resource sites, danger zones, request help, environment state
  - Base Station: resource site positions, danger zones
  - Mechanic: system info

- Sattelite:
  - All Bases: Bids
  - Drones: distribute missions

- Rover:
  - Drone: ---
  - Sattelite: malfunction
  - Base: relay data

  - Drone & Rover: current position, danger zones, request help, environment state
  - Base Station: resource site positions, danger zones
  - Mechanic: system info

- Base Station:
  - Sattelite: relay Bids
  - Drone: recharge
  - Rover: recharge

  - Drone & Rover: data collected, environment state when inside station, rover/drone arrivals and departures
  - Mechanic: rover/drone information

- Mechanic:
  - empty

== Planetary environment

- *Challenges*:
  - storms (dust storms, rain storms)
  - terrain obstacles
  - equipment malfunctions
  - dynamic environment agents (hostile or friendly)???
  
- *Locations and Resources*:
  - terrain dynamics (mountains, valleys, ...)
  - water spots, lakes, underground locations
  - minerals
  - caves

== Goals
- Maximize coverage of mapping
- Minimize redundancy
- Find resources
