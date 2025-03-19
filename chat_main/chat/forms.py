from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import User
from .models import Profile, Room
from django.db.models import Q
class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user

class UserProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=False, label='Имя')
    last_name = forms.CharField(max_length=30, required=False, label='Фамилия')
    email = forms.EmailField(required=True, label='Email')

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')

class ProfileForm(forms.ModelForm):
    birth_date = forms.DateField(
        required=False, 
        label='Дата рождения',
        widget=forms.DateInput(
            attrs={'type': 'date'}
        )
    )

    class Meta:
        model = Profile
        fields = ('bio', 'birth_date', 'avatar')
        labels = {
            'bio': 'О себе',
            'avatar': 'Аватар',
        }


class RoomCreationForm(forms.ModelForm):
    """Форма для создания групповой комнаты"""
    class Meta:
        model = Room
        fields = ['name', 'description', 'is_private']
        labels = {
            'name': 'Название комнаты',
            'description': 'Описание (необязательно)',
            'is_private': 'Приватная комната'
        }
        help_texts = {
            'is_private': 'Если комната приватная, в неё можно попасть только по приглашению'
        }
        
class RoomInvitationForm(forms.Form):
    """Форма для приглашения пользователей в комнату"""
    users = forms.ModelMultipleChoiceField(
        queryset=None,  # Будет установлено в __init__
        widget=forms.CheckboxSelectMultiple,
        label='Выберите друзей для приглашения'
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        room = kwargs.pop('room')
        super().__init__(*args, **kwargs)
        
        # Получаем друзей пользователя, которые ещё не в комнате
        friends = User.objects.filter(
            Q(sent_friendships__receiver=user, sent_friendships__status='accepted') |
            Q(received_friendships__sender=user, received_friendships__status='accepted')
        ).distinct().exclude(id__in=room.participants.all()).exclude(id=room.creator.id)
        
        self.fields['users'].queryset = friends