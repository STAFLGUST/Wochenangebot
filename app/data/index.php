<?php /* Schutz des Datenordners: direkter Aufruf liefert 404 (Daten nur über api/storage.php). */ http_response_code(404); exit;
