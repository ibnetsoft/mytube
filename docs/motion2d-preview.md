# Scene-bound 2D preview

In the STD scene's **영역 동작 지정** panel, prepare a repaired background and save five full-canvas transparent PNG patches: closed, half-open and open mouth, blink, and hair. The newest saved patch for each role is used. A repaired background is necessary to avoid leaving the original hair behind. The mask editor can import a grayscale mask proposal and lets the user erase and restore the patch.

**저장 패치로 4초 미리보기 만들기** queues a local preview. The project must have a finalized, SHA-256-identified narration and a recorded subtitle timeline; the selected scene must have at least four seconds before the next scene. The preview uses the first four seconds of that scene at 24 fps. It is a separate result and is not automatically assigned to the scene or submitted for publication.

The API binds every job to its owner, image, scene order, selected voice, five patch IDs and hashes, repaired background, and start time. The local worker rechecks these inputs before rendering, after rendering and after uploading. It also verifies file hashes and the 96-frame duration. Changes or cancellation reject stale work. A ready preview is hidden if its selected background, image, voice, scene order or saved patches change. Repeated clicks for the same inputs reuse the same job; retrying a failed job explicitly resets it.

The worker runs Rhubarb `phonetic` locally and maps its cues to three mouth shapes. This is approximate Korean lip sync and requires visual/audio review. The prototype uses CPU FFmpeg and does not call a paid AI video API. Set `AIR_MOTION2D_RHUBARB` to the local Rhubarb executable, with all of its bundled files and the temporary directory on ASCII-only paths on Windows; this computer defaults to `D:/AIRStudio/Tools/Rhubarb/1.14.0/rhubarb.exe`.
