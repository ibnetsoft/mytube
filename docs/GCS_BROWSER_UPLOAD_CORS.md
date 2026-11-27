# GCS browser uploads

The standard project upload flow sends image and video bytes directly to the
`air-studio-prod` GCS bucket using a short-lived V4 signed URL. The browser
must be allowed to send cross-origin `PUT` requests from `https://studio.airing.work`.
The bucket also needs `GET` and `HEAD` for browser previews and media reads.

The matching CORS rule is in `auth-web/gcs-cors.json`. Applying a CORS file
replaces the bucket's full CORS configuration, so inspect the current rules
first and preserve any other origins or methods that are still needed:

```sh
gcloud storage buckets describe gs://air-studio-prod --format="default(cors_config)"
gcloud storage buckets update gs://air-studio-prod --cors-file=auth-web/gcs-cors.json
```

The account applying the change needs permission to read and update bucket
metadata. After applying it, retry a video upload from the image page. In
DevTools, the GCS `OPTIONS` preflight should include
`Access-Control-Allow-Origin: https://studio.airing.work` and allow `PUT`;
the subsequent `PUT` should finish before the app calls the asset completion
endpoint.

This CORS rule only enables the browser-to-GCS transfer. It does not change
where the file is stored: the video bytes remain in GCS. The app's completion
endpoint separately saves asset metadata and the GCS object path in the project
record.
