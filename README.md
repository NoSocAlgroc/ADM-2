## ADM paper 2:Extending Graph Convolutional Networks with vertex compatibility models

This is a fork from the original [LightGCN pytorch implementation](https://github.com/gusye1234/LightGCN-PyTorch).

It has been modified to accept an additional parameter:

`--outModel=[dot,1Linear,2Linear,3Linear]`

Which decides the model to use in order to compute the compatibility scores between pairs of vertices.

The following is the same example command given in the original repository with our added option, indicating the program to use our best performing model:

` cd code && python main.py --decay=1e-4 --lr=0.001 --layer=3 --seed=2020 --dataset="gowalla" --topks="[20]" --recdim=64 --outModel=1Linear`

Note that it moves the directory to the code folder. If the user is already there only the second part that runs the main.py is necessary.
