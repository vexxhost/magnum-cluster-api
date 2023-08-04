# Create a Private/Project Network 

Access your network settings or dashboard. Left side menu under “Project” -> “Network” -> “Networks” 

Click on “Create Network”, a window will pop up asking for details: 

![create network](../static/user/create-cluster-with-existing-private-network/create-network.png)

Field “Network Name” we choose `test-321`, and in addition, a subnet associated with the network can be created in the following steps of this wizard. 

Click on “Next”: 

* **Subnet Name:** Choose a suitable name for the subnet (e.g., "test-321-subnet"). 
* **Network Address:** On this occasion we specified the CIDR as "10.0.20.0/24" to assign IP addresses in the range from 10.0.20.1 to 10.0.20.254. 

Click on “Next”: 

* **DNS Name Servers:** For our scenario we enter "1.1.1.1" as the DNS server for the subnet 

Click on “Create”

![crete network 2](../static/user/create-cluster-with-existing-private-network/create-network-2.png)
![crete subnet 1](../static/user/create-cluster-with-existing-private-network/create-subnet.png)
![crete subnet 2](../static/user/create-cluster-with-existing-private-network/create-subnet-2.png)


