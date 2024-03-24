# Upgrading in Atmosphere environment
In Atmosphere environment, Magnum cluster-api is embedded in the Magnum conductor container.
Therefore, to upgrade Magnum cluster-api in your atmosphere environment, developers have to build a new Magnum container image with the desired revision.
On the other hand, `magnum-cluster-api` repository has a Github workflow to build and push Magnum container images which include the latest Magnum cluster-api driver code. So developers can trigger this workflow to get new Magnum images with the latest code.

## To apply a new release
Once a new release is published, image build workflow is triggered automatically and new container images is published to `quay.io/vexxhost/magnum-cluster-api`. So there is no need to run images again and just need to upgrade the image ref in Atmosphere deployment code.
Run the following cmd to update all Magnum image tags in `Atmosphere` project.
```sh
earthly +pin-images
```
It will fetch the hash value of the current head image and set it in `roles/default/vars/main.yaml` file. Then you can run `ansible-playbook` command to deploy/upgrade atmosphere as normal.

## To apply main branch (not released yet)
If you want to apply patches merged into main branch but not released yet, you can follow this instruction.
- First, build new Magnum container images by running image workflow with `Push images to Container Registry` enabled at https://github.com/vexxhost/magnum-cluster-api/actions/workflows/image.yml.
- Once the workflow is successfully finished, new images will be pushed to `quay.io/vexxhost/magnum-cluster-api`. You can get the exact image tag hash value from the workflow log. (note: It will not promote images so need to get the exact image digest hash value.)
- Update the image tags in `roles/default/vars/main.yaml` of atmosphere project. https://github.com/vexxhost/atmosphere/blob/c7c0de94112448522abb8973483da82eb5f937a8/roles/defaults/vars/main.yml#L101-L105
- Run atmosphere playbook again.

Or you can just update the images on-fly using kubectl CLI in your Atmosphere environment once you know the image ref but this is not recommended.
```sh
kubectl set image sts/magnum-conductor magnum-conductor=${IMAGE_REF} magnum-conductor-init=${IMAGE_REF} -n openstack
kubectl set image deploy/magnum-api magnum-api=${IMAGE_REF} -n openstack
kubectl set image deploy/magnum-registry registry=${IMAGE_REF} -n openstack
```
