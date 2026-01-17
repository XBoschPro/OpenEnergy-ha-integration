## Implémentation de l'Intégration OpenEnergy

Cette intégration a été développée pour offrir une expérience "plug-and-play" pour la connexion de Home Assistant à la plateforme OpenEnergy. Elle orchestre l'authentification, la configuration du client FRP (Fast Reverse Proxy), et la mise à jour de la configuration de Home Assistant.

### Fonctionnalités Clés

-   **Authentification OAuth2**: L'intégration utilise le flux d'authentification OAuth2 standard de Home Assistant pour se connecter à Keycloak, le fournisseur d'identité d'OpenEnergy. Cela garantit une authentification sécurisée sans que l'utilisateur n'ait à manipuler de mots de passe ou de tokens.
-   **Gestion Automatique de l'Add-on FRP**: L'intégration gère l'installation et la configuration de l'add-on `openenergy_frpc`. Elle s'assure que le repository de l'add-on est ajouté à Home Assistant, que l'add-on est installé, et que sa configuration est mise à jour avec les informations récupérées depuis l'API OpenEnergy.
-   **Configuration Automatique du Tunnel FRP**: Après une authentification réussie, l'intégration contacte l'API OpenEnergy pour obtenir la configuration du tunnel FRP, y compris l'adresse du serveur, le port, le nom du tunnel, et le token d'authentification.
-   **Patch de la Configuration Home Assistant**: L'intégration vérifie et modifie si nécessaire le fichier `configuration.yaml` de Home Assistant pour activer le support du reverse proxy (`use_x_forwarded_for` et `trusted_proxies`). Si une modification est apportée, une notification persistante est affichée pour demander à l'utilisateur de redémarrer Home Assistant.

### Flux de Fonctionnement

1.  **Configuration de l'Intégration**: L'utilisateur ajoute l'intégration OpenEnergy via l'interface de Home Assistant.
2.  **Authentification**: L'utilisateur est redirigé vers la page de connexion de Keycloak pour s'authentifier.
3.  **Récupération de la Configuration**: Une fois authentifiée, l'intégration récupère la configuration du tunnel FRP depuis l'API OpenEnergy.
4.  **Bootstrap de l'Add-on**: L'intégration installe et/ou configure l'add-on `openenergy_frpc` avec les informations du tunnel.
5.  **Mise à Jour de la Configuration**: L'intégration s'assure que la configuration de Home Assistant est correcte pour le fonctionnement du reverse proxy.
6.  **Démarrage de l'Add-on**: L'add-on `openenergy_frpc` est démarré, établissant ainsi la connexion sécurisée.

Cette approche automatisée simplifie grandement la mise en place de la connexion à OpenEnergy et assure une configuration correcte et sécurisée.
