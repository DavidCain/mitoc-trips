from django.contrib import messages
from django.db import connections, transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, View

from ws import merge, models
from ws.decorators import admin_only


class AdminOnlyView(View):
    @method_decorator(admin_only)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    @property
    def dupes_redirect(self):
        return redirect(reverse('potential_duplicates'))


class PotentialDuplicatesView(AdminOnlyView, TemplateView):
    """ Show pairs of participants where the accounts may be duplicates. """

    template_name = 'duplicates/index.html'

    @property
    def potential_duplicates(self):
        """ Yield pairs of potential duplicates.

        Each pair of potential duplicates has the most recently active person
        listed last. It's suggested that the merge is done into that account.
        """
        cursor = connections['default'].cursor()
        cursor.execute(
            '''
            with dupe_groups as (
              select array_agg(id order by profile_last_updated desc, id desc) as dupes
                from ws_participant
               group by name
              having count(*) > 1
            union
              select array_agg(id order by profile_last_updated desc, id desc) as dupes
                from ws_participant
               where cell_phone != ''
               group by cell_phone
              having count(*) > 1
            ),
            potential_pairs as (
              select dupes[1] as new_participant,
                     unnest(dupes[2:]) as old_participant
                from dupe_groups
            )
            select old_participant,
                   new_participant
              from potential_pairs pp
                   left join ws_distinctaccounts da on
                      (da.left_id = pp.old_participant and da.right_id = pp.new_participant)
                   or (da.left_id = pp.new_participant and da.right_id = pp.old_participant)
             where da.id is null
            '''
        )
        pairs = [(row[0], row[1]) for row in cursor.fetchall()]

        # Map PKs back to objects that can be used easily in templates
        participants = models.Participant.objects.filter(
            pk__in=[pk for pair in pairs for pk in pair]
        ).select_related('emergency_info__emergency_contact', 'car')
        par_by_pk = {par.pk: par for par in participants}

        for old, new in pairs:
            yield (par_by_pk[old], par_by_pk[new])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['potential_duplicates'] = list(self.potential_duplicates)
        return context


class MergeParticipantsView(AdminOnlyView):
    """ Merge two duplicate accounts together. """

    def participants_from_pks(self):
        pks = [self.kwargs['old'], self.kwargs['new']]
        participants = models.Participant.objects.filter(pk__in=pks)
        if len(participants) != 2:
            raise ValueError("One or more of the participants doesn't exist.")
        return participants

    def post(self, request, **kwargs):
        old_par, new_par = int(kwargs['old']), int(kwargs['new'])
        try:
            participants = self.participants_from_pks()
        except ValueError:
            messages.error(request, f"Cannot merge {old_par} into {new_par}")
            return self.dupes_redirect

        corresponding_users = {par.pk: par.user_id for par in participants}
        with transaction.atomic():
            merge.migrate_user(
                corresponding_users[old_par], corresponding_users[new_par]
            )
            merge.migrate_participant(old_par, new_par)
        messages.success(request, f'Merged participant #{old_par} into #{new_par}')
        return self.dupes_redirect

    def get(self, request, **kwargs):
        return self.dupes_redirect


class DistinctParticipantsView(AdminOnlyView):
    """ Mark two seemingly related participants as being distinct. """

    def participants_from_pks(self):
        pks = [self.kwargs['left'], self.kwargs['right']]
        participants = models.Participant.objects.filter(pk__in=pks)
        if len(participants) != 2:
            raise ValueError("One or more of the participants doesn't exist.")
        return participants

    def post(self, request, **kwargs):
        try:
            left, right = self.participants_from_pks()  # Order doesn't matter
        except ValueError:
            messages.error(request, f"One or more participants are deleted.")
            return self.dupes_redirect

        models.DistinctAccounts(left=left, right=right).save()
        messages.success(
            request,
            f"Marked {left.name} (#{left.pk}) as distinct"
            f" from {right.name} (#{right.pk}).",
        )
        return redirect(reverse('potential_duplicates'))

    def get(self, request, **kwargs):
        return self.dupes_redirect
