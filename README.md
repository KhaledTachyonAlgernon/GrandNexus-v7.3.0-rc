# GrandNexus 6.5 (réparation de la 6.4 + couche du 15/05)

## Colab
```python
# optionnel (débloque 8 modules du 15/05, voir les 3 niveaux dans le fichier) :
# !pip install -q -r /content/GrandNexus/requirements-extra.txt
!unzip -q -o GrandNexus_v6.5.zip -d /content
%cd /content/GrandNexus
!python tools/smoke_test.py              # imports module par module (bugs vs dépendances absentes)
!python tools/integration_test.py        # démarrage + capacités
!python tools/lab_reasoning.py           # voie perception→raisonnement vs témoins + orchestrateur
!python tools/layer_runtime_test.py 3    # tout le système vivant sur un NexusCore démarré
```
```python
import sys; sys.path.insert(0, "/content/GrandNexus")
from grandnexus.boot import boot
gn = boot(); gn.print_report()
print(gn.modules()["text_reasoner"].answer("Tous les hommes sont mortels. Socrate est un homme. Socrate est-il mortel ?")["answer"])
print(gn.orchestrator.process_input("No reptiles are mammals. A snake is a reptile. Is a snake a mammal?")["output"][0])
gn.shutdown()
```
Historique : `!git log --oneline` · Résultats et décisions : `CARNET_DE_BORD.md`.
