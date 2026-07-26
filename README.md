## HostNFly Home Assistant

Intégration Home Assistant (custom component) pour exposer l’occupation et la
prochaine réservation de vos logements HostNFly.

### Installation (développement)

1. Copier le dossier `custom_components/hostnfly` dans votre instance HA.
2. Redémarrer Home Assistant.
3. Ajouter l’intégration via l’UI.

### Configuration

- Email et mot de passe HostNFly.
- Hôte API optionnel (par défaut `https://api.hostnfly.com`).
- Le mot de passe n'est pas stocké : une réauthentification peut être demandée si le token expire.

#### Utilisation avec `secrets.yaml`

Cette intégration supporte une configuration YAML, ce qui permet d’utiliser `!secret` pour masquer les identifiants.

Exemple dans `configuration.yaml` :

```yaml
hostnfly:
  email: !secret hostnfly_email
  password: !secret hostnfly_password
  host: !secret hostnfly_host
```

Exemple dans `secrets.yaml` :

```yaml
hostnfly_email: user@example.com
hostnfly_password: MonMotDePasseSuperSecret
hostnfly_host: api.hostnfly.com
```

La configuration YAML est importée sous forme de config entry au démarrage de Home Assistant.

### Entités créées

- `Occupation` par listing (`occupied` / `free`)
- `Occupant courant` par listing (nom)
- `Nombre d'occupants` par listing (nombre)
- `Réservation en cours` par listing (plage de dates + attributs)
- `Réservation suivante` par listing (plage de dates + attributs)

### Options

- Intervalle de mise à jour (minutes)
- Fenêtre de dates (lookback / lookahead)
