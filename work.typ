#set page(paper: "a4", margin: (x: 2cm, y: 1.5cm))
#set text(font: "New Computer Modern", size: 11pt)
#set par(justify: false, leading: 0.65em)

= SIA Workflow

== Agents Roles

- *Rover*:
  - *Liveness*: explore terrain, analyze soil samples, detect resources
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
