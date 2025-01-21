#  Evohaus Parking
Sensor to fetch electricity meter data for a parking space managed by evohaus

# Installation Steps

- **optional**  try it out with docker , before install it into your home assistant.

    ```
    docker run -p 8123:8123 --restart always -d --name homeassistant -v ${PWD}:/config   -e TZ=Australia/Melbourne   ghcr.io/home-assistant/home-assistant:latest
    ```

- copy the `evohaus_parking` to the `custom_components` folder 
- restart
- add the following entry in `configuration.yaml`

    ```
        sensor:                
          - platform: evohaus_parking
            username: !secret evohaus_parking_user
            password: !secret evohaus_parking_password  
    ```

- add the following secrets in `secrets.yaml`

    ```
    evohaus_parking_user: 'H20WXX_XX'
    evohaus_parking_password: 'XXXXXX'

    ```

-  restart 
