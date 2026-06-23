# Upgrading in Atmosphere environment

In Atmosphere environments, Magnum Cluster API is embedded in the Magnum
conductor container. The container image that carries this project is maintained
outside this repository by
[`vexxhost/docker-magnum`](https://github.com/vexxhost/docker-magnum).

## To apply a new release

Once a new Magnum image is available from the `docker-magnum` pipeline, update
the image reference in Atmosphere deployment code.

Run the following command in the `Atmosphere` project to update Magnum image tags:

```sh
earthly +pin-images
```

It fetches the digest for the current image and sets it in
`roles/default/vars/main.yaml`. Then you can run `ansible-playbook` to deploy or
upgrade Atmosphere as normal.

## To apply main branch (not released yet)

If you want to apply patches merged into this repository's `main` branch before
they are released, first update the `magnum-cluster-api` revision consumed by
`docker-magnum` and use the resulting Magnum image digest from that pipeline.
Then:

- Update the image tags in `roles/default/vars/main.yaml` of the Atmosphere
  project.
- Run the Atmosphere playbook again.

You can also update the images in place using `kubectl` once you know the image
reference, but this is not recommended:

```sh
kubectl set image sts/magnum-conductor magnum-conductor=${IMAGE_REF} magnum-conductor-init=${IMAGE_REF} -n openstack
kubectl set image deploy/magnum-api magnum-api=${IMAGE_REF} -n openstack
```
