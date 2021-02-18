"""Support for the EauFrance service."""
from datetime import datetime, timedelta, time
import pytz
import logging
import ast

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA

from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_NAME,
    CONF_DEVICE_CLASS,
    CONF_DEVICE_ID,
)

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

import requests

#from . import extract_start_stop, extract_value_units

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = "Data provided by {0}"

DEFAULT_NAME = "VC"

MIN_TIME_BETWEEN_UPDATES = timedelta(hours=1)

DEVICE_CLASS = {
    "H": "Height",
    "Q": "Flow",
}


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_DEVICE_ID, default=""): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): vol.In(DEVICE_CLASS),
    }
)


async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: Callable,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    name = config.get(CONF_NAME)
    device_class = config.get(CONF_DEVICE_CLASS)
    device_id = config.get(CONF_DEVICE_ID)

    efd = EauFranceData(hass, device_id, device_class)
    async_add_entities(
        [VigicruesSensor.current(name, efd)],
        True,
    )


class VigicruesSensor(Entity):
    """Implementation of an EauFrance sensor."""

    def __init__(self, name: str, efd: EauFranceData):
        """Initialize the sensor."""
        self._name = name
        self._efd = efd
        self._state = None

    @classmethod
    def current(cls, name, vcs):
        return cls(name, efd)

    @property
    def name(self) -> str:
        return self._name

    @property
    def unique_id(self) -> str:
        return self._efd.unique_id

    @property
    def state(self) -> Optional[str]:
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        return self._efd.unit_of_measurement

    @property
    def device_state_attributes(self):
        source = "EauFrance"
        return {ATTR_ATTRIBUTION: ATTRIBUTION.format(source)}


    def update(self):
        """Get the latest data from EauFrance and updates the state."""

        #try:
        self._efd.update(self.hass)
        #except:
        #    _LOGGER.error("Exception when getting EauFrance web update data")
        #    return

        self._state = self._vcs.data
        self._unit_of_measurement = self._vcs.unit


class EauFranceData():
    """Get the latest data from EauFrance."""

    def __init__(self, hass, device_id, device_class):
        self._device_id = device_id
        self._device_class = device_class
        self._time_zone = hass.config.time_zone
        self.data = None
        if device_class == "H":
            self._unit = "m"
        else:
            self._unit = "m³/s"


    @property
    def unique_id(self) -> str:
        return "efd_" + self._device_id + self._device_class


    @property
    def unit_of_measurement(self) -> str:
        return self._unit


    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self, hass) -> None:
        # get readings from MA website
        try:
            obs = self.get_first_reading()

            if obs is None:
                _LOGGER.warning("Failed to fetch data from EauFrance")
                return

            self.data = obs["resultat_obs"]
            if self._device_class == "Q":
                self.data /= 1000
                self.data = round(self.data, 1)
        except ConnectionError:
            _LOGGER.warning("Unable to connect to EauFrance URL")
        except TimeoutError:
            _LOGGER.warning("Timeout connecting to EauFrance URL")
        except Exception as e:
            _LOGGER.warning("{0} occurred details: {1}".format(e.__class__, e))


    def get_device_history_url(self) -> str:
        """
        Create url to get the last 4h of readings for this station
        Parameters
            device_id   
        see
        https://hubeau.eaufrance.fr/page/api-hydrometrie#/hydrometrie/observations
        """

        # example https://hubeau.eaufrance.fr/api/v1/hydrometrie/observations_tr?code_entite=O588251001&grandeur_hydro=Q&timestep=60&sort=desc&date_debut_obs=2021-02-16

        base_url="https://hubeau.eaufrance.fr/api/v1/hydrometrie/observations_tr"
        params = {
            "code_entite" : self._device_id,
            "grandeur_hydro": self._device_class,
            "timestep": "60",
            "sort": "desc"
            }

        now = datetime.now()
        now += self._time_zone.utcoffset(now)
        start_of_period = now - timedelta(hours = 4)
        params.update({"date_debut_obs" : start_of_period.strftime("%Y-%m-%dT%H:%M:%S")})

        all_params = '&'.join('{0}={1}'.format(key, val) for key, val in params.items())
        
        return base_url + "?" + all_params


    def get_results_data(self):
        url = self.get_device_history_url()
        response = requests.get(url)
        if response.status_code != requests.codes.ok:
            raise Exception("requests getting data: {0}".format(response.status_code))
        content = response.content.decode()
        #content = '{"count":10,"first":"https://hubeau.eaufrance.fr/api/v1/hydrometrie/observations_tr?code_entite=O588251001&grandeur_hydro=Q&timestep=60&sort=desc&date_debut_obs=2021-02-16&page=1&size=10","prev":null,"next":null,"api_version":"1.0.1","data":[{"code_site":"O5882510","code_station":"O588251001","grandeur_hydro":"Q","date_debut_serie":"2021-02-16T00:00:00Z","date_fin_serie":"2021-02-16T10:00:00Z","statut_serie":4,"code_systeme_alti_serie":31,"date_obs":"2021-02-16T10:00:00Z","resultat_obs":147629.0,"code_methode_obs":12,"libelle_methode_obs":"Interpolation","code_qualification_obs":16,"libelle_qualification_obs":"Non qualifiée","continuite_obs_hydro":true,"longitude":1.340482605,"latitude":44.091553707}]}'
        content = content.replace(":null", ":None")
        content = content.replace(":true", ":True")
        root = ast.literal_eval(content)
        d = root["data"]
        return d


    def get_first_reading(self) -> Dict[str, Any]:
        d = self.get_results_data()
        reading = {"date_obs": d[0]["date_obs"], "resultat_obs": d[0]["resultat_obs"]}
        return reading
