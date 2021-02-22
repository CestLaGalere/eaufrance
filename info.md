# EauFrance station data

## Installation

To install this integration you will need to add this as a custom repository in HACS.
Open HACS page, then click integrations
Click the three dots top right, select Custom repositories

1. URL enter <https://github.com/cestlagalere/eaufrance>
2. Catgory select Integration
3. click Add

Once installed you will then be able to install this integration from the HACS integrations page.

Restart your Home Assistant to complete the installation.

## Configuration

add elements to yaml sensor section:

    - platform: eaufrance
      name: montauban_flow
      device_class: Q
      device_id: O494101001

device_class - Q (Quantity of water - in m3 / s) H - river height (m)

device_id: id of the station

see either <https://hubeau.eaufrance.fr/api/v1/hydrometrie/referentiel/sites>

or the map at: <https://www.vigicrues.gouv.fr/niv2-bassin.php?CdEntVigiCru=25>

<https://hubeau.eaufrance.fr/api/v1/hydrometrie/api-docs>
