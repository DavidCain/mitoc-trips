from collections import defaultdict
from typing import List, Tuple

from ws import models


class Cycle:
    def __init__(self, participants: Tuple[models.Participant]):
        assert len(participants) > 1
        # Participants must be saved to the database (or they are unhashable)
        # (Also, we should never see participants blocking one another without being in the db!)
        assert all(par.pk is not None for par in participants)
        assert len(participants) == len(set(participants)), "Cycles can't repeat"

        # Participant collection might be modified later. Make an immutable copy now.
        self._cycle = tuple(participants)

    def __len__(self):
        return len(self._cycle)

    def __iter__(self):
        yield from self._cycle

    def __eq__(self, other):
        """ Return if two cycles represent the same cycle.

        Cycles need not be expressed in the same order to be equal.
        """
        if not isinstance(other, Cycle):
            return False
        if len(self) != len(other):
            return False

        # At this point, we know that the two cycles are the same size.
        # Only two things remain to differentiate them:
        # 1. Differing set of participants
        # 2. Differing order of blocks

        # Shift the two cycles to share a start (if needed, or if possible)
        starting_par = self._cycle[0]
        ordered_pks = tuple(par.pk for par in other)
        try:
            first_par_i = ordered_pks.index(starting_par.pk)
        except ValueError:
            return False  # The first participant is not in the other cycle
        if first_par_i != 0:
            ordered_pks = ordered_pks[first_par_i:] + ordered_pks[:first_par_i]

        return ordered_pks == tuple(par.pk for par in self)

    def __str__(self):
        pars = [f'{par.name} (#{par.pk})' for par in self._cycle]
        pars.append(pars[0])  # (complete the cycle)
        return ' --> '.join(pars) + '...'


class SeparationGraph:
    def __init__(self, relevant_participants):
        """ Create the graph, ignores blocks by or against any excluded participants.

        This allows us to easily ignore participants who have a separation request
        in place, but have not signed up for trips on a given Winter School week.
        """
        # Start with all relevant blocks. We'll remove nodes as we continue
        self._graph = self._make_graph(relevant_participants)

    @staticmethod
    def _make_graph(participants):
        """ Express all separations as a directed graph of participants.

        This graph may be a tree (a directed acyclic graph, or DAG) or it could have cycles.

        The most common expected incidence of cycles is a bi-directional block (two participants
        who have blocked one another).
        """
        # If a participant is not taking part in a lottery, their block isn't relevant.
        # Be sure to exclude any blocks that will falsely denote cycles
        relevant_blocks = models.LotterySeparation.objects.filter(
            initiator__in=participants, recipient__in=participants,
        )
        mapping = defaultdict(set)
        for block in relevant_blocks:
            mapping[block.initiator].add(block.recipient)
        return dict(mapping)

    @property
    def participants_affected_by_blocks(self):
        seen_recipients = set()
        for initiator, blocked in self._graph.items():
            yield initiator
            for recipient in blocked:
                if recipient not in self._graph and recipient not in seen_recipients:
                    yield recipient
                seen_recipients.add(recipient)

    @property
    def current_graph(self):
        return self._graph

    def remove(self, par):
        """ Mark a participant as handled, so remove them from the graph. """
        # None of the blocks made by this participant are relevant anymore!
        self._graph.pop(par, None)

        # There may be people blocking only this participant. We can remove them from the graph.
        participants_now_blocking_nobody = set()

        # Similarly, we don't need to consider any blocks by people towards this par
        for initiator, recipients in self._graph.items():
            recipients.discard(par)
            if not recipients:
                participants_now_blocking_nobody.add(initiator)

        for initiator in participants_now_blocking_nobody:
            self._graph.pop(initiator)

    @property
    def empty(self) -> bool:
        """ Return true if all participants have been handled. """
        # TODO: Should also allow a key with an empty set?
        return not bool(self._graph)

    def isolated_cycles(self, start_par) -> List[Cycle]:
        r""" Return any directed cycles containing this participant (with no terminal nodes reachable)

        If cycles are detected, we will eventually need to place one of the participants
        to break a potential race condition wherein all participants are waiting for
        another participant they've blocked to be placed.

        If there are no cycles, then no race condition is possible.

        If terminal nodes exist, then they should be handled first before breaking cycle.

        Examples: (argument is "A")
            True: at least one cycle, zero termini
            False: some termini and/or zero cycles

          # True: Bidirectional pairing

              A <----> B

          # True: Entire graph is a simple chordless cycle

            A ------> B
            ^         v
            |         |
            |         |
            +--< C <--+

          # True: All nodes in the graph are part of cycles

            A ------> B
            ^         |
            |         |
            |         v
            E ------> C
            ^         v
            |         |
            |         |
            +--< E <--+

          # False: start participant not in graph!

            B ----> C

          # False: graph is a tree (no cycles)

            A ---> B --> C
                   \
                    \--> D

          # False: part of a cycle, but there are nodes not part of a cycle

            A ------> B ---> D
            ^         v
            |         |
            |         |
            +--< C <--+
        """
        if start_par not in self._graph:
            return []

        termini = set()

        seen = {start_par}
        path = []

        def dfs(par):
            """ Depth-first search, starting with the participant

            Yield any found cycles, note if a terminal node is found.
            """
            nonlocal path, termini

            blocked_participants = self._graph.get(par, set())

            seen.add(par)
            path.append(par)

            if not blocked_participants:
                termini.add(par)
            for child in blocked_participants:
                if child not in seen:
                    yield from dfs(child)
                elif child in path:  # Current path contains a cycle!
                    # Make sure we report "A -> B -> C" if `child` is D in this scenario:
                    #   A ------> B <--- D
                    #   ^         v
                    #   +--< C <--+
                    just_cycle_subpath = path[path.index(child) :]
                    yield Cycle(tuple(just_cycle_subpath))

            path.pop()

        # Importantly, ignore any cycles that do not directly involve this participant.
        # (Also, exhaust the generator now, so as to set `termini`)
        member_cycles = [cycle for cycle in dfs(start_par) if start_par in cycle]
        return [] if termini else member_cycles
