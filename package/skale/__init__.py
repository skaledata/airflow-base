"""SkaleData Airflow extensions.

Namespace mirrors Airflow's own provider layout
(``airflow.providers.<name>.{hooks,operators,triggers}.<name>``) so that
SkaleData's drop-in replacements feel native:

    from skale.providers.airbyte.operators.airbyte import AirbyteTriggerSyncOperator

The plug-in payload, by default, talks to SkaleData-managed services
(Airbyte with ``global.auth.enabled=false``, etc.). Subsequent providers
slot in under ``skale.providers.*`` without changing this top-level
package.
"""

__version__ = "0.3.0"
