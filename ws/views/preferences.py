"""
Participant preference views.

Users can enroll in discounts, rank their preferred trips, or elect to be
paired with another participant. All of these options are deemed "preferences"
of the participant.
"""
import json
from typing import Dict, Set

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, FormView, TemplateView

from ws import enums, forms, models, tasks
from ws.decorators import user_info_required
from ws.mixins import LotteryPairingMixin
from ws.utils.dates import is_currently_iap, local_date


class LotteryPairingView(CreateView, LotteryPairingMixin):
    model = models.LotteryInfo
    template_name = 'preferences/lottery/pairing.html'
    form_class = forms.LotteryPairForm
    success_url = reverse_lazy('lottery_preferences')

    def get_context_data(self, **kwargs):
        """ Get a list of all other participants who've requested pairing. """
        context = super().get_context_data(**kwargs)
        self.participant = self.request.participant
        context['pair_requests'] = self.pair_requests
        context['currently_winter_school'] = is_currently_iap()
        return context

    def get_form_kwargs(self):
        """ Edit existing instance, prevent user from pairing with self. """
        kwargs = super().get_form_kwargs()
        kwargs['participant'] = participant = self.request.participant
        kwargs['exclude_self'] = True
        try:
            kwargs['instance'] = participant.lotteryinfo
        except models.LotteryInfo.DoesNotExist:
            pass
        return kwargs

    def form_valid(self, form):
        participant = self.request.participant
        lottery_info = form.save(commit=False)
        lottery_info.participant = participant
        self.add_pairing_messages()
        return super().form_valid(form)

    def add_pairing_messages(self):
        """ Add messages that explain next steps for lottery pairing. """
        self.participant = self.request.participant
        paired_par = self.paired_par

        if not paired_par:
            no_pair_msg = "Requested normal behavior (no pairing) in lottery"
            messages.success(self.request, no_pair_msg)
            return

        reciprocal = self.reciprocally_paired

        pre = "Successfully paired" if reciprocal else "Requested pairing"
        messages.success(self.request, f"{pre} with {paired_par}")

        if reciprocal:
            msg = (
                "You must both sign up for trips you're interested in: "
                "you'll only be placed on a trip if you both signed up. "
                "Either one of you can rank the trips."
            )
            messages.info(self.request, msg)
        else:
            msg = f"{paired_par} must also select to be paired with you."
            messages.info(self.request, msg)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class DiscountsView(FormView):
    form_class = forms.DiscountForm
    template_name = 'preferences/discounts.html'
    success_url = reverse_lazy('discounts')

    def get_queryset(self):
        available = Q(active=True)
        par = self.request.participant
        if not (par and par.is_student):
            available &= Q(student_required=False)
        return models.Discount.objects.filter(available)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['discounts'].queryset = self.get_queryset().order_by('name')
        return form

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.request.participant
        return kwargs

    def form_valid(self, form):
        form.save()
        participant = form.save()
        for discount in participant.discounts.all():
            tasks.update_discount_sheet_for_participant.delay(
                discount.pk, participant.pk
            )
        msg = (
            "Discounts updated! Ensure your membership "
            "is active for continued access to discounts."
        )
        messages.success(self.request, msg)
        return super().form_valid(form)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class LotteryPreferencesView(TemplateView, LotteryPairingMixin):
    template_name = 'preferences/lottery/edit.html'
    update_msg = 'Lottery preferences updated'
    car_prefix = 'car'

    @property
    def post_data(self):
        return json.loads(self.request.body) if self.request.method == "POST" else None

    @property
    def ranked_signups(self):
        # NOTE: In the future, we may support multi-trip lotteries outside WS
        # For now, though, this tool is only for ranking WS trips
        return (
            models.SignUp.objects.filter(
                participant=self.request.participant,
                on_trip=False,
                trip__algorithm='lottery',
                trip__program=enums.Program.WINTER_SCHOOL.value,
                trip__trip_date__gt=local_date(),
            )
            .order_by('order', 'time_created', 'pk')
            .select_related('trip')
        )

    @property
    def ranked_signups_dict(self):
        """ Used by the Angular trip-ranking widget. """
        return [
            {'id': s.pk, 'trip': {'id': s.trip.pk, 'name': s.trip.name}}
            for s in self.ranked_signups
        ]

    def get_car_form(self, use_post=True):
        car = self.request.participant.car
        post = self.post_data if use_post else None
        return forms.CarForm(post, instance=car, scope_prefix=self.car_prefix)

    def get_lottery_form(self):
        participant = self.request.participant
        try:
            lottery_info = participant.lotteryinfo
        except models.LotteryInfo.DoesNotExist:
            lottery_info = None
        return forms.LotteryInfoForm(self.post_data, instance=lottery_info)

    def get_context_data(self, **kwargs):
        self.participant = self.request.participant
        return {
            'currently_winter_school': is_currently_iap(),
            'ranked_signups': json.dumps(self.ranked_signups_dict),
            'car_form': self.get_car_form(use_post=True),
            'lottery_form': self.get_lottery_form(),
            'reciprocally_paired': self.reciprocally_paired,
            'paired_par': self.paired_par,
        }

    def post(self, request, *args, **kwargs):
        context = self.get_context_data()
        lottery_form = context['lottery_form']
        car_form = context['car_form']
        if not lottery_form.is_valid():
            # Could use lottery_form.errors to give a better message...
            return JsonResponse({'message': 'Lottery form invalid'}, status=400)

        skip_car_form = lottery_form.data['car_status'] != 'own'
        if skip_car_form or car_form.is_valid():
            if skip_car_form:  # New form so submission doesn't show errors
                # (Only needed when doing a Django response)
                context['car_form'] = self.get_car_form(use_post=False)
            else:
                self.request.participant.car = car_form.save()
                self.request.participant.save()
            lottery_info = lottery_form.save(commit=False)
            lottery_info.participant = self.request.participant
            if lottery_info.car_status == 'none':
                lottery_info.number_of_passengers = None
            lottery_info.save()
            try:
                self.save_signups()
            except (ValueError, TypeError):
                resp, status = {'message': 'Unable to save signups'}, 400
            else:
                self.handle_paired_signups()
                resp, status = {'message': self.update_msg}, 200
        else:
            resp, status = {'message': "Car form invalid"}, 400

        return JsonResponse(resp, status=status)

    def save_signups(self):
        """ Save the rankings given by the participant, optionally removing any signups. """
        par = self.request.participant
        posted_signups = self.post_data['signups']
        required_fields: Set[str] = {'id', 'deleted', 'order'}

        for ps in posted_signups:
            for key in required_fields:
                if key not in ps:
                    raise ValueError(f"{key} missing from {ps}")

        # First, delete any signups (provided they belong to the user & are lottery WS trips)
        # It's important that we prevent participants from deleting *other* signups with this route:
        # 1. Not all trips allow participants to drop off
        # 2. Signals aren't triggered from this `delete()`, which means FCFS logic isn't triggered
        to_del_ids = [p['id'] for p in posted_signups if p['deleted']]
        if to_del_ids:
            self.ranked_signups.filter(pk__in=to_del_ids).delete()

        # Next, explicitly rank signups that the participant listed
        order_per_signup: Dict[int, int] = {
            int(p['id']): int(p['order']) for p in posted_signups if not p['deleted']
        }
        signups = models.SignUp.objects.filter(participant=par, pk__in=order_per_signup)
        for signup in signups:
            signup.order = order_per_signup[signup.pk]
        models.SignUp.objects.bulk_update(signups, ['order'])

    def handle_paired_signups(self):
        """ For participants who might be paired, warn if other participant hasn't signed up.

        We can only place paired participants on a trip together if *both* of them have signed up.
        Accordingly, any paired participant trying to rank a trip for the two of them will be
        warned if the other half of the pairing hasn't signed up yet.
        """
        if not self.reciprocally_paired:
            return

        paired_par = self.paired_par
        # Don't just iterate through saved forms. This could miss signups
        # that participant ranks, then the other signs up for later
        for signup in self.ranked_signups:
            trip = signup.trip
            try:
                pair_signup = models.SignUp.objects.get(
                    participant=paired_par, trip=trip
                )
            except models.SignUp.DoesNotExist:
                msg = f"{paired_par} hasn't signed up for {trip}."
                messages.warning(self.request, msg)
            else:
                pair_signup.order = signup.order
                pair_signup.save()

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
