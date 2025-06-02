from typing import Optional

from ape.types.private_mempool import Bundle, SimulationReport
from ape.utils.basemodel import ManagerAccessMixin


class PrivateMempoolAPI(ManagerAccessMixin):
    """
    A wrapper around MEV APIs available through flashbots or reth.
    """

    def simulate_bundle(
        self, bundle: Bundle, sim_overrides: Optional[dict] = None
    ) -> SimulationReport:
        """
        Simulata bundle.

        Args:
            bundle (``Bundle``): The bundle of transactions to simulate.

        Returns:
            ``SimulationReport``: The results of the simulation.
        """
        bundle_request = {"bundle": bundle.model_dump(), "simOverrides": sim_overrides or {}}
        result = self.provider.make_request("mev_simBundle", bundle_request)
        return SimulationReport.model_validate(result)
