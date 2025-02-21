from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.loginPage, name='login'),
    path('register/', views.SignupPage, name='signup'),
    path('logout/', views.logoutUser, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/update/', views.update_profile, name='update_profile'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('profile/update-credentials/', views.update_credentials, name='update_credentials'),
    path('register-business/', views.register_business, name='register_business'),
    path('business/edit/', views.edit_business, name='edit_business'),
    path('business/settings/edit/', views.edit_business_settings, name='edit_business_settings'),
    path('business/credentials/edit/', views.edit_credentials, name='edit_credentials'),
    path('business/credentials/generate-secret/', views.generate_secret_key, name='generate_secret_key'),
    path('business/integrations/add/', views.add_integration, name='add_integration'),
    path('business/integrations/<int:pk>/edit/', views.edit_integration, name='edit_integration'),
    path('business/integrations/<int:pk>/delete/', views.delete_integration, name='delete_integration'),
]