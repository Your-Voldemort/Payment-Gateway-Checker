"""Fast gateway pre-filter using the Aho-Corasick algorithm.

This module no longer carries its own pattern catalog. Instead it builds an
Aho-Corasick automaton from *literal anchors* supplied by :mod:`detection`
(the single source of truth for gateway patterns). That removes the catalog
drift that previously made this module dead code, and lets detection use the
automaton as a sound pre-filter.

How the pre-filter stays correct
--------------------------------
``detection`` extracts, for each regex pattern, a literal substring that is
*guaranteed* to be present whenever that regex can match (and marks a gateway
as "always run" when no such anchor can be safely extracted). The automaton
finds every anchor present in a page in a single O(n) pass, yielding the set of
gateways that *could* match. Gateways whose anchors are all absent cannot match,
so detection can safely skip their (more expensive) regex tiers — without ever
dropping a gateway the full scan would have found.

Performance: Aho-Corasick matches all anchors simultaneously in O(n + m) where
n = text length and m = number of matches, versus O(n * p) for running every
pattern. The win grows with the volume of text scanned (e.g. the multi-page /
JS-bundle deep scan).

Falls back to a plain substring sweep if ``pyahocorasick`` is not installed, so
the bot keeps working (just without the speedup).
"""

from typing import Dict, Iterable, List, Set
from logger import setup_logger

logger = setup_logger()

# Try to import pyahocorasick, fall back to a substring sweep if unavailable.
try:
    import ahocorasick
    AHOCORASICK_AVAILABLE = True
    logger.info("Aho-Corasick algorithm available for gateway pre-filtering")
except ImportError:
    AHOCORASICK_AVAILABLE = False
    logger.warning("pyahocorasick not installed, using substring-sweep fallback")


class GatewayPrefilter:
    """Maps the literal anchors present in a page to candidate gateway names.

    Args:
        anchors: ``{gateway_name: [literal_anchor, ...]}`` — anchors are matched
            case-insensitively (they are lowercased on ingest).
        always_run: gateways that must always be treated as candidates (used for
            patterns from which no safe literal anchor could be extracted).
    """

    def __init__(self, anchors: Dict[str, List[str]], always_run: Iterable[str] = ()):
        self._always: Set[str] = set(always_run)

        # anchor (lowercased) -> set of gateways that have a pattern with that anchor
        anchor_map: Dict[str, Set[str]] = {}
        for gateway, anchor_list in anchors.items():
            for anchor in anchor_list:
                a = (anchor or "").lower()
                if a:
                    anchor_map.setdefault(a, set()).add(gateway)
        self._anchor_map = anchor_map

        self._automaton = None
        if AHOCORASICK_AVAILABLE and anchor_map:
            automaton = ahocorasick.Automaton()
            for anchor, gateways in anchor_map.items():
                automaton.add_word(anchor, frozenset(gateways))
            automaton.make_automaton()
            self._automaton = automaton

        logger.debug(
            f"GatewayPrefilter built: {len(anchor_map)} anchors, "
            f"{len(self._always)} always-run gateways, "
            f"backend={'aho-corasick' if self._automaton else 'substring'}"
        )

    @property
    def uses_ahocorasick(self) -> bool:
        return self._automaton is not None

    @property
    def always_run(self) -> Set[str]:
        return set(self._always)

    def candidates(self, text: str) -> Set[str]:
        """Return the set of gateways that could plausibly match *text*.

        This is a *superset* of the gateways the full regex scan would find:
        anchorless gateways are always included, and any gateway whose anchor is
        present is included. Gateways excluded here provably cannot match.
        """
        found: Set[str] = set(self._always)
        if not text:
            return found
        low = text.lower()

        if self._automaton is not None:
            for _end_index, gateways in self._automaton.iter(low):
                found |= gateways
        else:
            for anchor, gateways in self._anchor_map.items():
                if anchor in low:
                    found |= gateways
        return found


def is_ahocorasick_available() -> bool:
    """Check if the Aho-Corasick optimization is available."""
    return AHOCORASICK_AVAILABLE
