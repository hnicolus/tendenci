def init_signals():
    from django.db.models.signals import post_save
    from tendenci.addons.resumes.models import Resume
    from tendenci.apps.contributions.signals import save_contribution

    post_save.connect(save_contribution, sender=Resume, weak=False)