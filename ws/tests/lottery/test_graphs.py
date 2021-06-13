from ws.lottery import graphs
from ws.tests import TestCase, factories


class CycleTests(TestCase):
    def test_catches_too_short_cycles(self):
        par = factories.ParticipantFactory.create()
        with self.assertRaises(AssertionError):
            graphs.Cycle([])
        with self.assertRaises(AssertionError):
            graphs.Cycle([par])

    def test_catches_unsaved_participants(self):
        one = factories.ParticipantFactory.build()
        two = factories.ParticipantFactory.build()
        with self.assertRaises(AssertionError):
            graphs.Cycle([one, two])

    def test_catches_repeated_participants(self):
        bert = factories.ParticipantFactory.create(name="Bert")
        ernie = factories.ParticipantFactory.create(name="Ernie")
        with self.assertRaises(AssertionError):
            graphs.Cycle([bert, ernie, bert])
        graphs.Cycle([bert, ernie])

    def test_cycle_of_two(self):
        bert = factories.ParticipantFactory.create(name="Bert")
        ernie = factories.ParticipantFactory.create(name="Ernie")
        cycle = graphs.Cycle([bert, ernie])
        self.assertEqual(len(cycle), 2)
        self.assertEqual(
            str(cycle),
            f'Bert (#{bert.pk}) --> Ernie (#{ernie.pk}) --> Bert (#{bert.pk})...',
        )
        self.assertEqual(list(cycle), [bert, ernie])
        self.assertEqual(cycle, graphs.Cycle([ernie, bert]))

    def test_cycle_of_three(self):
        rock = factories.ParticipantFactory.create(name="Rock")
        paper = factories.ParticipantFactory.create(name="Paper")
        scissors = factories.ParticipantFactory.create(name="Scissors")

        # Rock blocks scissors, which blocks paper, which blocks rock
        cycle = graphs.Cycle([rock, scissors, paper])
        self.assertEqual(len(cycle), 3)
        self.assertEqual(list(cycle), [rock, scissors, paper])

        # So long as ordering is preserved, cycle start does not matter
        self.assertEqual(cycle, graphs.Cycle([scissors, paper, rock]))
        self.assertEqual(cycle, graphs.Cycle([paper, rock, scissors]))

        # This ordering is different!
        self.assertNotEqual(cycle, graphs.Cycle([scissors, rock, paper]))

        # Sorry, Flula - not equivalent (though it is better)
        dynamite = factories.ParticipantFactory.create(name="Dynamite")
        self.assertNotEqual(cycle, graphs.Cycle([rock, scissors, dynamite]))

    def test_differing_types_unequal(self):
        bert = factories.ParticipantFactory.create(name="Bert")
        ernie = factories.ParticipantFactory.create(name="Ernie")
        cycle = graphs.Cycle([bert, ernie])
        self.assertNotEqual(cycle, [bert, ernie])
        self.assertNotEqual(cycle, (bert, ernie))
        self.assertNotEqual(cycle, {bert, ernie})

    def test_same_length_differing_contents(self):
        a, b, c, d = (factories.ParticipantFactory.create(name=l) for l in 'ABCD')

        self.assertNotEqual(graphs.Cycle([a, b]), graphs.Cycle([c, d]))

    def test_differing_sizes_unequal(self):
        rock = factories.ParticipantFactory.create(name="Rock")
        paper = factories.ParticipantFactory.create(name="Paper")
        scissors = factories.ParticipantFactory.create(name="Scissors")
        lizard = factories.ParticipantFactory.create(name="Lizard")
        spock = factories.ParticipantFactory.create(name="Spock")

        self.assertNotEqual(
            graphs.Cycle([rock, paper, scissors]),
            graphs.Cycle([rock, paper, scissors, lizard, spock]),
        )


class GraphTests(TestCase):
    def setUp(self):
        self.outside_graph_par = factories.ParticipantFactory.create()

    def _make_graph(self, pars):
        return graphs.SeparationGraph([self.outside_graph_par, *pars])

    @staticmethod
    def _make_block(initiator, recipient):
        factories.LotterySeparationFactory.create(
            creator=initiator,  # (Should require an admin, but save db hits)
            initiator=initiator,
            recipient=recipient,
        )

    def test_no_blocks(self):
        graph = self._make_graph([])
        self.assertTrue(graph.empty)
        self.assertFalse(graph.isolated_cycles(self.outside_graph_par))
        self.assertCountEqual(graph.participants_affected_by_blocks, [])

    def test_bidirectional_blocking(self):
        """ Test two participants blocking each other.

            A <----> B
        """
        a = factories.ParticipantFactory.create(name="A")
        b = factories.ParticipantFactory.create(name="B")
        self._make_block(a, b)
        self._make_block(b, a)

        graph = self._make_graph([a, b])
        self.assertCountEqual(graph.participants_affected_by_blocks, [a, b])
        self.assertEqual(graph.current_graph, {a: {b}, b: {a}})

        expected_cycle = graphs.Cycle([a, b])
        self.assertEqual(graph.isolated_cycles(a), [expected_cycle])
        self.assertEqual(graph.isolated_cycles(b), [expected_cycle])

        graph.remove(a)
        self.assertTrue(graph.empty)

        self.assertFalse(graph.isolated_cycles(a))
        self.assertFalse(graph.isolated_cycles(b))

    def test_chordless_cycle_graph(self):
        """ Test three participants blocking in a cycle

            A ------> B
            ^         v
            |         |
            |         |
            +--< C <--+
        """
        a = factories.ParticipantFactory.create(name="A")
        b = factories.ParticipantFactory.create(name="B")
        c = factories.ParticipantFactory.create(name="C")
        self._make_block(a, b)
        self._make_block(b, c)
        self._make_block(c, a)

        graph = self._make_graph([a, b, c])
        self.assertCountEqual(graph.participants_affected_by_blocks, [a, b, c])
        self.assertEqual(graph.current_graph, {a: {b}, b: {c}, c: {a}})

        expected_cycle = graphs.Cycle([a, b, c])
        self.assertEqual(graph.isolated_cycles(a), [expected_cycle])
        self.assertEqual(graph.isolated_cycles(b), [expected_cycle])
        self.assertEqual(graph.isolated_cycles(c), [expected_cycle])

        graph.remove(a)
        self.assertEqual(graph.current_graph, {b: {c}})
        self.assertFalse(graph.isolated_cycles(a))
        self.assertFalse(graph.isolated_cycles(b))
        self.assertFalse(graph.isolated_cycles(c))

    def test_multiple_cycles(self):
        """ Test two cycles existing.

            A ------> B
            ^         |
            |         |
            |         v
            E ------> C
            ^         v
            |         |
            |         |
            +--< D <--+
        """
        a, b, c, d, e = (
            factories.ParticipantFactory.create(name=letter) for letter in "ABCDE"
        )
        self._make_block(a, b)
        self._make_block(b, c)
        self._make_block(c, d)
        self._make_block(d, e)
        self._make_block(e, a)
        self._make_block(e, c)

        all_pars = [a, b, c, d, e]
        graph = self._make_graph(all_pars)
        self.assertCountEqual(graph.participants_affected_by_blocks, all_pars)
        self.assertEqual(
            graph.current_graph, {a: {b}, b: {c}, c: {d}, d: {e}, e: {a, c}}
        )

        for par in all_pars:
            graph.isolated_cycles(par)
            self.assertTrue(graph.isolated_cycles(par))

        graph.remove(e)
        for par in all_pars:
            self.assertFalse(graph.isolated_cycles(par))

    def test_graph_is_a_tree(self):
        r""" Test when the directed graph is just a tree (has no cycles)

             A ---> B --> C
                    \
                     \--> D
        """
        a, b, c, d = (
            factories.ParticipantFactory.create(name=letter) for letter in "ABCD"
        )
        self._make_block(a, b)
        self._make_block(b, c)
        self._make_block(b, d)

        all_pars = [a, b, c, d]
        graph = self._make_graph(all_pars)
        self.assertCountEqual(graph.participants_affected_by_blocks, all_pars)
        self.assertEqual(graph.current_graph, {a: {b}, b: {c, d}})

        for par in all_pars:
            self.assertFalse(graph.isolated_cycles(par))

    def test_cycle_exists_but_with_termini(self):
        """ Test when the directed graph has a cycle, but has termini

            A ------> B ---> D
            ^         v
            |         |
            |         |
            +--< C <--+
        """
        a, b, c, d = (
            factories.ParticipantFactory.create(name=letter) for letter in "ABCD"
        )
        self._make_block(a, b)
        self._make_block(b, c)
        self._make_block(b, d)
        self._make_block(c, a)

        all_pars = [a, b, c, d]
        graph = self._make_graph(all_pars)
        self.assertCountEqual(graph.participants_affected_by_blocks, all_pars)
        self.assertEqual(graph.current_graph, {a: {b}, b: {c, d}, c: {a}})

        self.assertFalse(graph.isolated_cycles(b))
        for par in all_pars:
            self.assertFalse(graph.isolated_cycles(par))

        graph.remove(d)
        self.assertFalse(graph.isolated_cycles(d))
        expected_cycle = graphs.Cycle([a, b, c])
        for par in [a, b, c]:
            self.assertEqual(graph.isolated_cycles(par), [expected_cycle])

    def test_cycle_exists_with_extra_nodes_but_no_termini(self):
        """ Test when the directed graph has a cycle and non-directionally relevant nodes!

            A ------> B <--- D
            ^         v
            |         |
            |         |
            +--< C <--+
        """
        a, b, c, d = (
            factories.ParticipantFactory.create(name=letter) for letter in "ABCD"
        )
        self._make_block(a, b)
        self._make_block(b, c)
        self._make_block(c, a)
        self._make_block(d, b)

        all_pars = [a, b, c, d]
        graph = self._make_graph(all_pars)
        self.assertCountEqual(graph.participants_affected_by_blocks, all_pars)
        self.assertEqual(graph.current_graph, {a: {b}, b: {c}, c: {a}, d: {b}})

        # D is not part of the cycle
        self.assertFalse(graph.isolated_cycles(d))

        # A, B, and C are, though!
        expected_cycle = graphs.Cycle([a, b, c])
        self.assertEqual(graph.isolated_cycles(a), [expected_cycle])
        self.assertEqual(graph.isolated_cycles(b), [expected_cycle])
        self.assertEqual(graph.isolated_cycles(c), [expected_cycle])

    def test_cycle_exists_but_with_irrelevant_participans(self):
        """ Participant B is not in this lottery! There's no cycles in this case.

            A -----> (B) --> D
            ^         v
            |         |
            |         |
            +--< C <--+
        """
        a, b, c, d = (
            factories.ParticipantFactory.create(name=letter) for letter in "ABCD"
        )
        self._make_block(a, b)
        self._make_block(b, c)
        self._make_block(b, d)
        self._make_block(c, a)

        all_pars = [a, b, c, d]
        relevant_pars = [a, c, d]
        self.assertNotIn(b, relevant_pars)
        graph = self._make_graph(relevant_pars)
        self.assertCountEqual(graph.participants_affected_by_blocks, [a, c])
        self.assertEqual(graph.current_graph, {c: {a}})

        for par in all_pars:
            self.assertFalse(graph.isolated_cycles(par))
