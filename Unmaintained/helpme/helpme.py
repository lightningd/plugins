#! /usr/bin/env python3
from pyln.client import Plugin, Millisatoshi, RpcError
from collections import defaultdict
from functools import wraps
from os import path
import random
import threading

plugin = Plugin()

# How many peers we want
DESIRED_PEERS = 3

# These about 1 tenth of the nodes which have been around for about 6 months.
known_nodes_mainnet = {
    '0204a2b95b4c208383d7f02e741a8bfd5b5b7e8bea8d1543b1255da8342d9f2c6b':
    [{"type": "ipv4", "address": "172.81.178.189", "port": 9735}],
    '02098684c9d7a9ec27071faf09f1442c228a8778c01903a45eafefc43212ae4385':
    [{"type": "torv3", "address": "l75fjgfirm3ria7q3kgr4eelm2t5siwgwairzf6y54hnq6kbuddcehid.onion", "port": 9735}],
    '020ca546d600037181b7cbcd094818100d780d32fd9f210e14390e0d10b7ec71fb':
    [{"type": "ipv4", "address": "94.214.185.162", "port": 9742}],
    '0211e23e154bb0b87c210b92b3ed07071ee6168cdfcd24132db8e8fdb5eccba976':
    [{"type": "ipv4", "address": "187.65.218.133", "port": 9735}],
    '0216006237022044d9bdb73ca51af267c5f67cf76095b4c6275f1162eb422fed68':
    [{"type": "ipv4", "address": "108.7.50.215", "port": 9735}],
    '0219fc8bad855d3c861166a89d637950242230fd3d475bb4a2d1da8c89b97beb0a':
    [{"type": "ipv4", "address": "185.228.137.102", "port": 9735}],
    '021f05bd7bec2dacaafa9eea30e3c2dd64a1eee699c3aad6aeca8a5c6dd6ed3198':
    [{"type": "ipv4", "address": "78.94.255.174", "port": 9735}],
    '02272bd12e59324d0f2b231fb88f134b57eb26dd100d2cc007df50f18aa12455a2':
    [{"type": "ipv4", "address": "35.198.182.182", "port": 9735}],
    '022d2c907ef13d7e36ac1c61e788ba7c9d979b33be1ea21c421796eb11c44d5260':
    [{"type": "ipv4", "address": "80.110.71.162", "port": 9735}],
    '023062afced94dc97f5d756f94099b46b25407df418d3b4cf43d03dea3417cdc43':
    [{"type": "ipv4", "address": "138.197.162.95", "port": 9735}],
    '0232c9cdca608482d3d4990b8b8dabcd6b1a5d09cc3ba6b284a372a037ee26d993':
    [{"type": "ipv4", "address": "96.49.88.110", "port": 9735}],
    '02379f8ffd4e080f2a9ee5ada5e02c6be5625eb93dfadd45fb9aabe69ea97e3595':
    [{"type": "ipv4", "address": "116.227.55.191", "port": 9735}],
    '023aa85c3ab7f5492db500283b8b4aff89325651e768642e7bcb270ad9eb16d04d':
    [{"type": "ipv4", "address": "35.188.42.255", "port": 9735}],
    '024098e05cd67fc8b1dcd0edf0c12b441c1e1f0db3d953ea84229abc279e1079b2':
    [{"type": "ipv4", "address": "46.38.245.95", "port": 9735}],
    '0246b7010a84e5335a606355a638acfc6d35de98dca8c9931e940908e0de008e04':
    [{"type": "ipv4", "address": "191.114.191.6", "port": 9735}],
    '024b00cf3368dbff39daa6de5638cd877b96227066e1e0d31b10183daa63ac325d':
    [{"type": "ipv4", "address": "94.156.174.22", "port": 9735}],
    '024ed53fa7065f409749c8caebf058289bbf392c3e282e9c843de2c6d28bb80f9a':
    [{"type": "ipv4", "address": "173.56.53.60", "port": 9735}],
    '0255b0812589b3d10657655394bea298cd9f2033d9220f313607eb495291f2a729':
    [{"type": "ipv4", "address": "89.142.129.59", "port": 9735}],
    '025a65cb44fdfc83254dca89e73b8bf4edbca8d93e10826361765a4941fdddcda4':
    [{"type": "ipv4", "address": "194.99.104.19", "port": 9735}],
    '0260fab633066ed7b1d9b9b8a0fac87e1579d1709e874d28a0d171a1f5c43bb877':
    [{"type": "ipv4", "address": "54.245.57.153", "port": 9735}],
    '02655822e2b03f889c83b5ce23b0951ee077c206a5e588efe331c8197c207dbd1c':
    [{"type": "ipv4", "address": "35.230.20.234", "port": 9735}],
    '0269b91661812bae52280a68eec2b89d38bf26b33966441ad70aa365e120a125ff':
    [{"type": "ipv4", "address": "82.36.141.97", "port": 9735},
     {"type": "torv3", "address": "qe5lvu5g72s7edly4xu4gon3qbx7xca2fnfutifvfptr5lv2xrt4doid.onion", "port": 9735}],
    '026c49329e78135c5c2c479fe48b711dc97abd6a6f9d834b701cd44d99d6d2378e':
    [{"type": "ipv4", "address": "73.228.40.96", "port": 9735}],
    '0271e3c8a038756dda07a07ea8d77ffd545210c021cd62147e80d7500a7336403f':
    [{"type": "ipv4", "address": "35.196.226.101", "port": 9735}],
    '027962b0b105025f1c7fc87aa4b618bb847fd38e6d0a583cd1ac4d8d0a2a568891':
    [{"type": "ipv4", "address": "173.249.59.243", "port": 9735}],
    '027cb5b394c5330467081901dba14d48a4ac0f10012e5791e725a65d326405a82e':
    [{"type": "ipv4", "address": "82.40.164.125", "port": 9735}],
    '02827a7ba367d10a29f0a178be878f737292889d1926b40301780d7e1402a90a72':
    [{"type": "ipv4", "address": "18.223.138.245", "port": 9735}],
    '02866bd9513e4e82f250c9b8a0b83cabc9be3c4824f7016bd160859d0fad3d8920':
    [{"type": "ipv4", "address": "82.23.106.56", "port": 9735}],
    '0289b175772f8f2d17dda83a08cba18bf1f0484019cf5abde7fa69acb9a52652f7':
    [{"type": "ipv4", "address": "178.128.165.102", "port": 9735}],
    '028dcc199be86786818c8c32bffe9db8855c5fca98951eec99d1fa335d841605c2':
    [{"type": "ipv4", "address": "153.126.136.98", "port": 9735}],
    '029196b18f91a0d1ab53adfde49fa381b0e228f1b6fe7623ef2a1023b7ef2dcedc':
    [{"type": "ipv4", "address": "35.196.44.113", "port": 9735}],
    '02986d2a01e7955583f04876f5b6219e0741e43ebaa00246232106bade5b429498':
    [{"type": "ipv4", "address": "159.65.202.160", "port": 9735}],
    '029d50d59c78b81a39f4ca40b6bc9b89710542a31429b69aa075b91b587979205d':
    [{"type": "ipv4", "address": "185.228.137.238", "port": 9735}],
    '02a1849aeeae8e71fa0487d7229957da6d0e1f927266b5854ea800f6b7a323a423':
    [{"type": "ipv4", "address": "35.228.174.168", "port": 9735}],
    '02a5d937fd2328e1a48fd56769ab6ea810fa9c67bfac233f0ac864494b5442d483':
    [{"type": "ipv4", "address": "82.94.35.199", "port": 9735}],
    '02ae3c06f6db6a87ea874ef7ba86c87ab0041eabf6d8be0594582505b1fd5d7ee8':
    [{"type": "ipv4", "address": "76.103.92.123", "port": 9735}],
    '02b414e4e29a685b8699152be47a0420fa3c8ab59629d2da2d6c0a95c582636350':
    [{"type": "ipv4", "address": "149.56.200.57", "port": 9735}],
    '02b714dfb1961b719df4a8c06371c0b547ec5dfaa4faf39beabd8974d6b60fe5a3':
    [{"type": "ipv4", "address": "46.5.120.69", "port": 9735}],
    '02be74034df42a6cefa7d204ac726393f07a2b2cac9cee07400056c3512b6c2271':
    [{"type": "ipv4", "address": "50.46.125.169", "port": 9736}],
    '02c119d2fd2e98a88f50d0d2ee4213255b7b8ec2be3a95f9aabd6afb09dd25b083':
    [{"type": "ipv4", "address": "98.186.249.155", "port": 9735}],
    '02c42da239071be3a0990924f542e782d4fd09c128d4a2b41b6cae195bdd1ee12e':
    [{"type": "ipv4", "address": "92.116.121.174", "port": 9735}],
    '02cb72d6aebc1c29e7e8e3066bdc01e4608b39968b8054307387424aeebe3a25c6':
    [{"type": "ipv6", "address": "2a02:908:2221:cc80:6f3f:7ad3:8151:9f14", "port": 9735}],
    '02cffd722f871b8f064130d2879027c9b169a95ab6ccedbaea4ade7b5d0678ff67':
    [{"type": "ipv4", "address": "130.193.15.73", "port": 9735}],
    '02d776ab8db0f62572e0435a70a5f3f3b2ee803357cbef9f915720a9d377a71c6b':
    [{"type": "ipv4", "address": "181.166.65.202", "port": 9735}],
    '02dc523b9db431de52d7adb79cf81dd3d780002f4ce952706053edc9da30d9b9f7':
    [{"type": "ipv4", "address": "185.200.117.131", "port": 64338}],
    '02e0742d2acb105f0d68a285419b3334c89cac6a1c97c98b7845c3428b6d74b9cf':
    [{"type": "ipv4", "address": "47.187.239.188", "port": 9735}],
    '02e7c42ae2952d7a71398e23535b53ffc60deb269acbc7c10307e6b797b91b1e79':
    [{"type": "ipv4", "address": "93.123.80.47", "port": 9735}],
    '02ef8eee471a04b6f5bc9eb69a2ea9625e71f3b93a5ee7dc6350474730cd1f29c9':
    [{"type": "ipv4", "address": "213.133.108.178", "port": 9735},
     {"type": "ipv6", "address": "2a01:4f8:130:632c::2", "port": 9735}],
    '02f40890af885da4673f0ee9725ee74bb2c66d6491cc4334056a2701057993e61d':
    [{"type": "ipv4", "address": "88.198.91.250", "port": 9735},
     {"type": "torv3", "address": "blackwort4i27cvp4l4l45nq7iebyjyib5lfwqzdpgiznqtlzu3c7jid.onion", "port": 9735}],
    '02fd98ebd4cbedd1317d629d62d192cf943f0134c61464de48f1e232d861de4ef9':
    [{"type": "ipv4", "address": "52.55.248.131", "port": 9735}],
    '03026fa633c5b04dc1d30f1fdc5c4c052661fbb0e3d8136c1bc310041e6569a931':
    [{"type": "ipv4", "address": "217.63.228.164", "port": 9735}],
    '0307a3fb98c026148e69f51f1851b41db6dc2abf58e77e588636a60ce85c82f091':
    [{"type": "ipv4", "address": "46.4.79.166", "port": 9735}],
    '031005495ec32c915c992930a0a9471e9b832fd77d133d8417729084779a308b1a':
    [{"type": "ipv4", "address": "163.172.106.188", "port": 9735}],
    '03144fcc73cea41a002b2865f98190ab90e4ff58a2ce24d3870f5079081e42922d':
    [{"type": "ipv4", "address": "5.9.83.143", "port": 9735}],
    '031ac677972619e8e0a1b40593e01b04280dc4a18a7a9b5cb7c6e8e2673e31f644':
    [{"type": "ipv4", "address": "91.121.174.41", "port": 9765},
     {"type": "ipv6", "address": "2001:41d0:1:ef29::1", "port": 9766}],
    '031f751bd251f6682dea57eac04275a1d8e2abc5f91b8fa929f8730bc292d56536':
    [{"type": "ipv4", "address": "93.244.131.64", "port": 9735}],
    '03238e5f00ed7e8bc3ebddb7d18ca81d50c7f1f50a7158388d650f14514249c720':
    [{"type": "ipv4", "address": "178.193.79.101", "port": 9735}],
    '0329e41996f9e314600ef72e373981194eb2aa48474cbc244f883bc87b7db32591':
    [{"type": "ipv4", "address": "163.172.174.151", "port": 9735}],
    '032d4baebebfdeab7a2ecef2fbe109cbef10de95f05aa54090fdb687789547dbf5':
    [{"type": "ipv4", "address": "212.51.146.119", "port": 9735}],
    '0332317f2fdeab6fe83675ffde9d8092b5bdedcf7ab6e6c2dcac62a149f8eae8e1':
    [{"type": "ipv4", "address": "35.185.26.80", "port": 9735}],
    '033613d280de1eba995c7545e93caf76cfba41bef88c2d6732a67ce06c168b3acb':
    [{"type": "ipv4", "address": "124.18.45.201", "port": 9735}],
    '033c87f6e5e202a4569d6d074da09cad4210a25bb89f00d6f53caa7429f6e55eed':
    [{"type": "ipv4", "address": "83.213.102.133", "port": 9735},
     {"type": "ipv4", "address": "85.86.30.194", "port": 9735}],
    '0342284b265ce9542f7d6d98f64715b2d4571de54acfd343fd4abc90663fd250b5':
    [{"type": "ipv4", "address": "212.108.220.138", "port": 9735}],
    '034955913a44e335be62b4e9ee33be036f72d150302163d2cd02ae6546ce9ce899':
    [{"type": "ipv4", "address": "77.181.173.236", "port": 9735}],
    '034cfb8dcb453372e8f13915cc770bcd7bb0f0809dd1b47c0c3b43b969ff9ff3b7':
    [{"type": "ipv4", "address": "206.189.62.95", "port": 9735}],
    '035287f7d8e7301660ed7e660a7baabb4c344326951c1739f9d930937adc82030e':
    [{"type": "ipv4", "address": "104.219.251.104", "port": 9735}],
    '0356c02ffe265f8ff38471e901785528d3da0668cd0a590ed67ee809d929c9bfd4':
    [{"type": "ipv4", "address": "18.195.199.190", "port": 9735}],
    '035a002c71bc9ffb0026ee505323f143055bf1dedd4ec878e5a1b68c792f363eba':
    [{"type": "ipv6", "address": "::", "port": 9735}],
    '035f460a31af1a03db7965575923735bdfdc96c2ac3e78cec63c9e08c3c9b8a529':
    [{"type": "ipv4", "address": "35.229.68.186", "port": 9735}],
    '036265cf7c7356b06b9d64a09dad1c7f7519971be475100ca893b2ff2c5120e4dd':
    [{"type": "ipv4", "address": "24.186.159.133", "port": 9735}],
    '0367e072b7b6e40e5df3fbf8701bf1bc7efce021a5702dac7d0a9be7bb59f1f01c':
    [{"type": "ipv4", "address": "203.218.141.157", "port": 9735}],
    '036e6d0bda4e1a071b1e41208e8aa257ac9015285b08f4a080cd3ed57e3faac907':
    [{"type": "ipv4", "address": "31.17.18.240", "port": 9735}],
    '0372fe303fabd8caaefaa31ebc90478bccd6cbaddeaf3b9d8c42a67ef07f77d281':
    [{"type": "torv3", "address": "je2sab6opr2ioanrvtkfkbvcwp6vbisucjnzzm65ubhlvhqy4jcx6vid.onion", "port": 9735}],
    '0376a33371c17cd4fab6c1202f8031b4c899a53cc89739dd411d5b924afcd6cc7f':
    [{"type": "ipv4", "address": "82.64.60.174", "port": 9735}],
    '037d706d809b71937dfeab0cc0577018d31bca5a729605529c5fe746924b2562bb':
    [{"type": "ipv4", "address": "35.231.92.48", "port": 9735}],
    '03830ecd6fefbfc926a35ba474e56bb7466402570843b4936fbd984b7fbb213ac7':
    [{"type": "ipv6", "address": "2a01:4f8:13b:3810::2", "port": 9735}],
    '03878111c5c4b86749f5af107a7cc7d097472f672e59a6b511d92b958e3df352c5':
    [{"type": "ipv4", "address": "220.244.251.214", "port": 9735}],
    '038bcc6471941c7d6c14a8ce5b7159d8f73a3a0bb9a93e8896bcb892e14552658a':
    [{"type": "ipv4", "address": "83.162.155.18", "port": 9735}],
    '039044f8cc91c1069f1747fe237fe0e1d626abee240eaaf3f9b21b99fd9c8231c7':
    [{"type": "ipv6", "address": "2607:fa48:6c08:1070:699d:badd:c64b:11da", "port": 9735}],
    '039437e5ba3cd7168394d08fd1e423a613084e3d30d31d8069a6ded0921bc5b6b6':
    [{"type": "ipv4", "address": "37.8.237.243", "port": 9735}],
    '039b3ec0c8ce6a322a7fe6c7b246bcd40471702e4b58a81f4caa0261ff6fdbf486':
    [{"type": "ipv4", "address": "35.185.53.169", "port": 9735}],
    '03a17e8ec9570e1b71d1c719aeeafa88b0604068863dc88028b490b96c2898dda8':
    [{"type": "ipv4", "address": "95.216.13.45", "port": 9735}],
    '03a5fd566492a69f3653ca464c23d8678ec19634c440baa9a1366c9b39c89512cd':
    [{"type": "ipv4", "address": "79.136.31.253", "port": 9735}],
    '03a9b9b4d5bff67fb90d7deaf7db842e3aa5e3abea58fa488a8af3d163679107d7':
    [{"type": "ipv4", "address": "118.163.74.161", "port": 9735},
     {"type": "ipv6", "address": "2001:b030:2422::208d", "port": 9735}],
    '03ad7fe66e7b95e9db50696488a029315cd0e22b7cd36d344eb53e52742abfced6':
    [{"type": "ipv4", "address": "91.190.22.151", "port": 9735}],
    '03b490b2f840dcc5038528740203d59183991554e34fca0f38e45896c6b0a403a2':
    [{"type": "ipv4", "address": "79.225.184.134", "port": 9735}],
    '03b9aacb265dc5ebde04b91b28f7c8bb6ba0af146e5f37426915742daf8f195a09':
    [{"type": "torv2", "address": "fmibpwpimunb4kwm.onion", "port": 9735},
     {"type": "torv3", "address": "6dvvxicvwba7553srqm3kk7euyrlh2h6qhpghcw6nu7dqdgdnzcyfqid.onion", "port": 9735}],
    '03beddc8adbf7d56a7da15cdaf95d97b24d07088c3571b421c0e6f9d551a210342':
    [{"type": "ipv4", "address": "148.251.40.218", "port": 9735}],
    '03c409d19b1d3dbb2191e28ba150e89273675fcf2812b58ac3fd88bb98abed41f1':
    [{"type": "ipv4", "address": "35.190.144.254", "port": 9735}],
    '03c8be501a366c2807cd065313b3faf9521003d8c9f1bbd175d0dec7da212adbfc':
    [{"type": "ipv4", "address": "35.185.117.112", "port": 9735}],
    '03cfe33b1a2170acea4e3a29acf5a2a3abd22ae9a615182d39893a9f3645f0eb7c':
    [{"type": "ipv4", "address": "174.16.206.3", "port": 9735}],
    '03d4b06f17456c936c7b14a0ceb370581e8574946b8e4aef630e14a6eb8a178ea6':
    [{"type": "ipv4", "address": "185.67.204.76", "port": 9735}],
    '03dbe3fedd4f6e7f7020c69e6d01453d5a69f9faa1382901cf3028f1e997ef2814':
    [{"type": "ipv4", "address": "35.196.214.59", "port": 9735}],
    '03e24db0341fff731e24aeb0492e54510d1392d21d121a51e644ac5797300d495f':
    [{"type": "ipv4", "address": "46.101.112.24", "port": 9735}],
    '03e8f8e8666030a241a5d790cef81625620650621fb4aa7f0dca867c90e2e2c083':
    [{"type": "ipv4", "address": "35.231.14.198", "port": 9735}],
    '03ee180e8ee07f1f9c9987d98b5d5decf6bad7d058bdd8be3ad97c8e0dd2cdc7ba':
    [{"type": "ipv4", "address": "85.214.212.104", "port": 9735}],
    '03f2d334ab70d50623c889400941dc80874f38498e7d09029af0f701d7089aa516':
    [{"type": "ipv4", "address": "158.174.131.171", "port": 9735}],
    '03f810ac5ca2edf9e7908b4edf98411a26b555d8aee6b1c9a0a5ad62b9359aa546':
    [{"type": "ipv4", "address": "81.7.17.202", "port": 9735},
     {"type": "ipv6", "address": "2a2:180:6:1::3e", "port": 9735}],
    '03fcdbd95bfd6479a09ff87cf8d9a58a38dcd0dcbeab7ad524b770c91d5a0aef14':
    [{"type": "ipv4", "address": "79.150.30.182", "port": 9735}],
}

# For testnet, my test net node, ACINQs and a few randoms
known_nodes_testnet = {
    '031a3478d481b92e3c28810228252898c5f0d82fc4d07f5210c4f34d4aba56b769':
    [{"type": "ipv4", "address": "165.227.30.200", "port": 9735},
     {"type": "ipv6", "address": "2604:a880:2:d0::2065:5001", "port": 9735}],
    '03933884aaf1d6b108397e5efe5c86bcf2d8ca8d2f700eda99db9214fc2712b134':
    [{"type": "ipv4", "address": "34.250.234.192", "port": 9735},
     {"type": "torv3", "address": "iq7zhmhck54vcax2vlrdcavq2m32wao7ekh6jyeglmnuuvv3js57r4id.onion", "port": 9735}],
    '02b07ad03c1b6181b9a56a1bd03d594d9a33f76a88d834801d3991a66e8695a067':
    [{"type": "ipv4", "address": "18.213.80.234", "port": 9735}],
    '02ffc14f1121d014f390f1978f347be8891a3e82b93ea99079389f954d1168a4b5':
    [{"type": "ipv4", "address": "83.175.99.67", "port": 9735}],
    '02f1a9f8c67e262ed0f1bcb43f06d1bec2889e8c99f407eb0ea29f90e26ed129e3':
    [{"type": "ipv4", "address": "82.202.205.99", "port": 19735}],
    '02c5422ff05df6cebcad76ac7cbe4795e2c5e15483bbfdb53e2f7ce7ff733cc177':
    [{"type": "ipv4", "address": "85.144.208.174", "port": 9735}],
    '0269a94e8b32c005e4336bfb743c08a6e9beb13d940d57c479d95c8e687ccbdb9f':
    [{"type": "ipv4", "address": "197.155.6.38", "port": 9735}],
    '03ce72ba8a5fc69a9cc6809fb757d6e3ac2f90682355acadb0e3788b8bbafdbc6c':
    [{"type": "ipv4", "address": "76.201.148.44", "port": 9735},
     {"type": "ipv6", "address": "2600:1700:3c40:1660:9c37:180f:acdd:50eb", "port": 9735}],
    '024490af0b7df1ad3104b2b968ac8089d3a38c23f1624801978694aa6015c4c655':
    [{"type": "ipv4", "address": "173.177.255.61", "port": 9735}],
    '02a78ed15da84d0ecdcefff5905bd7287ff587b7abd9a46cf0a04d31c3336a9b4e':
    [{"type": "ipv4", "address": "73.33.112.94", "port": 9735}],
    '0340a5ef77a609691ceff9163c73d35f548f692824ecfe155bb0c781b8715906f0':
    [{"type": "torv3", "address": "uecbeodu7yst35ud56akudnfyw6r7ylzdfnf5e5c6xmisdswrlunjcyd.onion", "port": 9735}],
    '0347dd556485e1adbcf46a8efaeac9ab5beb3efd0ba89eb7832c6e5a1391c68aec':
    [{"type": "ipv4", "address": "13.230.24.176", "port": 9739}],
    '02d08e965e4d4e6fd50ef9d4ed565be9a5585a9998e4f9c93c6f9af43a1e26b927':
    [{"type": "ipv6", "address": "::", "port": 9735}],
    '0349b73a3f6c4e719589162232535a67a4f0912a1ca9d7621af4b9753a8a5c782c':
    [{"type": "ipv4", "address": "54.194.9.112", "port": 9735}],
    '030465c8f35752bd22174c5f3d83ed95c0e404887a83d9466be2e58c7c03bb6346':
    [{"type": "ipv4", "address": "35.196.250.223", "port": 9735}],
    '023aa79fa287a7261d1cde062f464370709d18a0172fdbf17057326b53b48b0810':
    [{"type": "ipv4", "address": "82.202.205.99", "port": 29735}],
    '03cf50e2fa5c5bf30422e995d06b28a1a73ad038edd817d65afebd430db29521a0':
    [{"type": "ipv4", "address": "95.216.204.92", "port": 30000}],
    '0230d84c21cb2be5a00e64d2704ebe2ff80602523480d8625d9532ba78302debe2':
    [{"type": "ipv4", "address": "176.9.89.217", "port": 2000}],
    '03552f0a36588ed1003eb85cb85af5725d4ddf4a13bfea76d11c2bbd4812e02e00':
    [{"type": "ipv4", "address": "54.153.106.53", "port": 9735}],
    '031ac7acd69e041031242a09fce5b56d36dd8aab18e9745dde3199baedfb2a768a':
    [{"type": "ipv4", "address": "165.227.36.187", "port": 9735}],
    '024d6d0b7a1623858aba4974442129cce3f2505535e0e933e0b7e33cd7940c43d5':
    [{"type": "ipv4", "address": "84.30.230.162", "port": 9735}],
    '03da1d0544685ede4fcd80b0d300201ef743c4428c094bfb34a92f3f727f07a26a':
    [{"type": "ipv4", "address": "115.66.160.53", "port": 9735}],
    '03fe8b515eb339544c6ba2fe49f605c9353de98a50ff163f0c784b1c6249a91ddc':
    [{"type": "ipv4", "address": "104.248.18.227", "port": 9735}],
    '03d16880554137a1a7bcf3e57d0811e936f6132876c2fa331377fc5bf5b539c1c4':
    [{"type": "ipv4", "address": "128.171.163.79", "port": 9735}],
    '022176f285685300d4e09baf2e4656722f43220d269afebaa5bf21daf8daab87aa':
    [{"type": "ipv4", "address": "52.56.155.92", "port": 9735}],
    '0278c61016d71e47bc0b39c8794129228093212db8621c9ab087fd707d9ca26ba6':
    [{"type": "ipv4", "address": "179.108.19.226", "port": 9735}],
    '03dbbbc95d1132140d70eb425c4cfc75873f2c7fb738988e8f50b56fecc6ac889e':
    [{"type": "ipv4", "address": "82.124.11.9", "port": 9735}],
    '029ecdab6b189af9fed8cd6322a4c0209862438587f02357f92d83595056648b40':
    [{"type": "ipv4", "address": "108.70.247.57", "port": 9735}],
    '0279cef4090c32881cfc018e99c86a68cbdde2a7780caf41f6e9a17f53e4e96ee2':
    [{"type": "ipv4", "address": "62.216.208.222", "port": 9735}],
    '0374532c1846d0326de80ec67ff41bda992018da4e02ae183e1f9f82608127a8c3':
    [{"type": "ipv4", "address": "35.175.102.26", "port": 9735}],
    '03f8f6cbafc6e094ac9e085aa820cf32f1a0f3155e7571e28cdb727830d1421683':
    [{"type": "ipv4", "address": "159.69.195.167", "port": 9735}],
    '0394b69751d4e3d1b75aee4328ae4e5667c1c3bf39c9a3c4d4ef5943a3c13143e3':
    [{"type": "ipv6", "address": "2a02:810a:8a80:275c:3b72:c6a5:138f:ff56", "port": 9735}],
    '02fd08ff2f77bc413921974bfb789312083ac6692991b91eb90c2a554628a4ecc4':
    [{"type": "ipv4", "address": "131.196.147.26", "port": 9735}],
    '03e48474b377d38369fd7ea04a7c3871fbe0a105d325528a2da16c30e2bee22375':
    [{"type": "ipv4", "address": "187.66.70.104", "port": 9735}],
    '026bb9ede35f8874b4ea28b551c9cc846cc510d1ac5729ef92b9935fbd9ec1cc10':
    [{"type": "ipv4", "address": "71.105.65.102", "port": 9735}],
    '023b431c093e9599a17ee86f339f8f3105e5f69bdbe72b0a71f79635f1319731ef':
    [{"type": "ipv4", "address": "163.117.166.53", "port": 9935}],
    '032d6352948539151ba3a575e0d7835ce0e495387906ddbace6aae16cfb8d0ff37':
    [{"type": "ipv4", "address": "86.16.26.51", "port": 9735}],
    '02ad77dbfc33853c4effa2aa198bea23a61ce4f1e2a908c0cf5f88bdd196888a97':
    [{"type": "ipv4", "address": "99.81.67.66", "port": 9735}],
    '024f243e7def4a69a7b2327eae7cede8b68c0f27b602ee5a4be58cf30f24e5d583':
    [{"type": "ipv4", "address": "18.130.3.141", "port": 9735}],
    '035fad18d230f3acc2aad33dd993be870a781270182cc3f1f74f1ad39b2ebd34a5':
    [{"type": "ipv4", "address": "84.59.61.241", "port": 9738}],
    '0228922d73ff8764502fd70e6e24229c2387b7d0ac472264b12697c668521610d3':
    [{"type": "ipv4", "address": "69.164.201.194", "port": 9735}],
    '03977f437e05f64b36fa973b415049e6c36c0163b0af097bab2eb3642501055efa':
    [{"type": "ipv4", "address": "82.196.97.86", "port": 9735}],
    '02ffa8264720893618a6b7f3c2f21ec2cd6b8b1c5f60f8ba74eaf04d8fba99e653':
    [{"type": "ipv4", "address": "103.240.162.84", "port": 9735}],
    '030f375d8aecdddc852309c15c3b67c2934de0de4d31e1e04a03d656ca0a78d008':
    [{"type": "ipv4", "address": "104.131.26.124", "port": 9735}],
    '03874527d8049a5c85868623f5bb07985cb702bac58857bd43aff32d3c584f547b':
    [{"type": "ipv4", "address": "110.140.172.168", "port": 9735}],
    '03c437f533ff60a26a337f2c8cdd30d0f1882cf50b2854695032caf1722c997f08':
    [{"type": "ipv4", "address": "89.0.104.214", "port": 9735}],
    '032f60337c6721a1ca61bac1b705702aa999ed4670085f5de261c0c46222d41534':
    [{"type": "ipv4", "address": "74.210.177.223", "port": 9735}],
    '02c8e44339ca0ad55ff2176f2cad249c5071843ed2567829f963ff615001eada13':
    [{"type": "ipv4", "address": "24.228.183.56", "port": 19735}],
    '03fd3eb21a010c8d047c2ad0b888ebe06cdd411f83c2284488318bb1fd785b65c5':
    [{"type": "ipv4", "address": "34.74.169.236", "port": 9735}],
    '028f7496e5d6d36641f2eb47a4cb6c55c01ad1879ebe96423eea609ef87fdd2f86':
    [{"type": "ipv4", "address": "54.147.111.145", "port": 9735}],
    '023f1a19f60af6888c886f1342acd7a8256aa9b2884ca60a23d04cc9c22e3b74f5':
    [{"type": "ipv4", "address": "96.29.239.184", "port": 9735}],
    '038b093fbc0788be05658c631060a152f86fb523c51ad114856d4e03c3a059d419':
    [{"type": "ipv4", "address": "138.197.101.172", "port": 9735}],
    '03f5ecb876e25251c2def88e7dc74e9f221fe18c517b8e22873d451ba550189fb1':
    [{"type": "ipv4", "address": "52.56.155.92", "port": 9735}],
    '02da1a4fe9b0188ea755142af430ffbf4fca26ee8b2d735d6a1c83f1a8ad47b8e7':
    [{"type": "ipv4", "address": "52.166.88.225", "port": 9735}],
    '02971dab769f06ecc12f64dc9a8b0fad5387176f28614705f93a432298fb0f9efd':
    [{"type": "ipv4", "address": "114.241.176.231", "port": 9735}],
    '0291e55bccf1d1e4886ab0024cc6bcd5cd0c6d57f629276f8b30031e9ab0350597':
    [{"type": "ipv4", "address": "80.8.84.33", "port": 9735}],
    '030d1fc725449595a191820ea59b7ea8a8623c730bda1b4c498d377b8dfaf18324':
    [{"type": "ipv4", "address": "104.12.66.70", "port": 9735}],
    '031ae684606c385969d817152544a50fa66266f0822482733bcebe9007893aa7ee':
    [{"type": "ipv4", "address": "127.0.0.1", "port": 9735}],
    '022c876579e4c2cad198115fcff28c92199069fd8a59ba26b60431744b93b05f37':
    [{"type": "ipv4", "address": "159.65.83.241", "port": 9735}],
    '03b882dcd309adaf4d66d1aadfbc6e85764bd65c6bdaf03689c55f1abd13f53fc5':
    [{"type": "ipv4", "address": "95.216.101.105", "port": 9735}],
    '0225f906558f702a826a5a14eefee483d6ea03ea4f2abd62d34114dd9a78d29ebf':
    [{"type": "ipv4", "address": "5.95.80.47", "port": 9735}],
    '021180a15b8852ff6e512d3326ccd0836a4afac3f1a9e7bdb04f95eed425615b16':
    [{"type": "ipv4", "address": "93.55.248.42", "port": 9735}],
    '0374628b5c69a6655c1b98860697a1ce3c2ab99fdc58cbf2b6f6aa7a4efdf8f064':
    [{"type": "ipv4", "address": "35.246.205.63", "port": 9735}],
    '0354e3976b70016c5fe5df2e21748ba4475e247f9692f6f82deacd35f295efd45b':
    [{"type": "ipv4", "address": "69.140.11.86", "port": 9735}],
    '037df4e5b688f2d992e127801f8078e3b5195b2c5f0aa68d952377fcd05e046337':
    [{"type": "ipv4", "address": "181.168.101.234", "port": 9735}],
    '022b03498503fd78888c5f6748983c176acde255938ba1caac9b4730cff52c63cb':
    [{"type": "ipv4", "address": "85.195.200.124", "port": 9735}],
    '03e62ca7679da9683367b10f2f7a9f9a33581335f56616e5f13c8ebf938f6ce9f0':
    [{"type": "ipv4", "address": "78.45.17.49", "port": 9735}],
    '031736b7c87d0f14398cd114410e61dbdff110ace11ab71202e8634ff62e219f49':
    [{"type": "ipv4", "address": "69.250.227.245", "port": 9735}],
    '02c10c3c06f702b311d0e55edd4dc50fe0a3bf10d3e6f93f6def1ee5f2f3315bc4':
    [{"type": "ipv4", "address": "49.151.97.178", "port": 9735}],
    '03f2297213af13b2f61c8881ac96c896d3a5dc53e3a4163d2c594f82d94f8b69a2':
    [{"type": "ipv4", "address": "35.185.74.242", "port": 9735}],
    '0299761a3f71e30b57851a8d257efffb53c9e4e12fc05eb05eb629cfd517ba0021':
    [{"type": "ipv4", "address": "159.69.21.84", "port": 9737}],
    '0342fde872547df5a3be7726328cbf2d9fbcc7aead617245deb4fef86353934bd2':
    [{"type": "ipv4", "address": "207.246.75.123", "port": 9735}],
    '029acd76d581901375281c7489720cea277d25252832dadb6f0327f621673c8096':
    [{"type": "torv3", "address": "dxu2n6mfoiqzcc7i2mc6bxfcmylcngeoxgxvboidghw4ic5psrfyd6yd.onion", "port": 9735}],
    '03e5f9d1935c67a029bf0a26af5f63109f4f4c45993a8f45177a8f2f39bcb46144':
    [{"type": "ipv4", "address": "84.246.200.122", "port": 9735}],
    '029cc41810f968059892a13c3e08ed8ad2f45267f1545e77c5f850d6b177eb63fa':
    [{"type": "ipv4", "address": "95.174.125.24", "port": 9735}],
    '034eedf763483d461bac5fe689f5a3cf599f359a3588a323d8f1f43d92ba12fabc':
    [{"type": "ipv4", "address": "50.79.227.81", "port": 9735}],
    '02b5195a2378808d2fc87aa4cb4fb985fb6d459e86f861f383eba4d27a116167b2':
    [{"type": "ipv4", "address": "54.196.81.194", "port": 9735}],
    '03b46c5222c373ce95353d1ef1ecc8728cb53f54f4253f129a9062aa35f9a737fd':
    [{"type": "ipv4", "address": "159.89.230.135", "port": 9735}],
    '035cc46bd30aff9bad94ff82af52e3d73f980ed29ab7f1274f7efa41759dfc5dac':
    [{"type": "ipv4", "address": "178.62.81.192", "port": 9735}],
    '0387e89ea3fa2f73d6ec0293ab59114873db5113bfe0cc83083a4c3dc545e13265':
    [{"type": "ipv4", "address": "95.31.9.47", "port": 9735}],
    '0328f46ce2d0fe39ed920d7e846f93ce91b440080b42c08aee4ecc8a0d73974e8c':
    [{"type": "torv2", "address": "vmc6yv6mu6run6zd.onion", "port": 9735}],
    '0270dd534325064f5cdb8707672244a51e45f2bea6919e8614a03965e48c106de9':
    [{"type": "ipv4", "address": "185.200.118.101", "port": 9735}],
    '0388082ef17afb126db9a0877e5f8a8c1a88aec86107fd1f26c2503c384c570fdc':
    [{"type": "ipv4", "address": "159.89.29.186", "port": 9735}],
    '024e7585ab8feaf75628c4438a5290d7a9e3698c8cd51c4a89dc6e81f2d3ae2d42':
    [{"type": "ipv4", "address": "77.27.181.229", "port": 9745}],
    '024c7faea76f9437c12f2815afaff712721ffdb612e81c80bada5bcc0f8969f1d8':
    [{"type": "ipv4", "address": "78.133.43.170", "port": 9735}],
    '0303ba0fed62039df562a77bfcec887a9aa0767ff6519f6e2baa1309210544cd3d':
    [{"type": "ipv4", "address": "5.9.150.112", "port": 9735}],
    '02b252dd1f2769beccd50378ac99319637c6bb988206e1c181bec4bcb10a97f815':
    [{"type": "ipv4", "address": "118.163.74.161", "port": 19735}],
    '022cfa8589eb544358e2a94f849d15319e6356a443b4fb11668fdc113692681034':
    [{"type": "ipv4", "address": "2.238.196.161", "port": 9735}],
    '030444f1a4807f97612c8c6d5f9e4c9e75b96059dd99ccb14b6b39bb962104cf4d':
    [{"type": "ipv4", "address": "0.0.0.0", "port": 9735}],
    '0207a77f9012103a9e557f14e80f445946002b2752390b86554d7ca13eb1e6e0e9':
    [{"type": "ipv4", "address": "5.102.145.58", "port": 9735}],
    '032720f82414c8ce006d67004398b99697ae3f076c090745d6440ae3c3ade2af45':
    [{"type": "ipv4", "address": "66.70.135.170", "port": 19735}],
    '02b0ee0e06112db6929b1bc861d3659c608c61e5ab5899e02d417d1986ae0ab485':
    [{"type": "ipv4", "address": "204.48.26.93", "port": 9735}]
}


def get_channel_list(peers, state='CHANNELD_NORMAL'):
    channels = []
    for p in peers:
        if 'channels' in p:
            channels += p['channels']
        elif 'num_channels' in p and p['num_channels'] > 0:
            channels += plugin.rpc.listpeerchannels(p['id'])['channels']
        else:
            raise RpcError("helpme", {}, "RPC does not return channels")

    return [c for c in channels if state is None or c['state'] == state]


def give_general_advice(plugin):
    r = """Welcome to Core-Lightning!

The lightning network consists of bitcoin channels between computers
(like this one), and the ability to send those bitcoins between them.

It's still beta sofware, so DON'T PUT TOO MUCH MONEY in your lightning
node!  Be prepared to lose your funds (but please report a bug if you do!)
"""

    peers = plugin.rpc.listpeers()['peers']
    info = plugin.rpc.getinfo()
    funds = plugin.rpc.listfunds()['outputs']
    payments = plugin.rpc.listpays()['pays']
    invoices = plugin.rpc.listinvoices()['invoices']
    channels = get_channel_list(peers, None)

    if info['network'] != 'bitcoin':
        r += "\n*** You are on TESTNET, not real bitcoin!  See 'helpme mainnet'"

    stages = {'funds': False,
              'peers': False,
              'channels': False,
              'payments': False,
              'invoices': False,
              'bling': False}

    r += "\nSTAGE 1 (funds): "
    if len(funds) == 0 and len(channels) == 0:
        r += "INCOMPLETE: No bitcoins yet.  Try 'helpme funds'"
    elif len(funds) == 0 and len(channels) > 0:
        r += "COMPLETE (all funds used for channels)"
    else:
        funds = Millisatoshi(sum([f['amount_msat'] for f in funds
                             if f['status'] == 'confirmed']))
        r += "COMPLETE ({} a.k.a. {})".format(funds, funds.to_btc_str())
        stages['funds'] = True

    r += "\nSTAGE 2 (peers): "
    if len(peers) == 0:
        r += "Not connected to the network.  Try 'helpme peers'"
    else:
        r += "COMPLETE ({} peers)".format(len(peers))
        stages['peers'] = True

    r += "\nSTAGE 3 (channels): "
    starting = [c['total_msat'] for c in channels
                if c['state'] == 'CHANNELD_AWAITING_LOCKIN']
    normal = [c['total_msat'] for c in channels
              if c['state'] == 'CHANNELD_NORMAL']
    ending = [c['total_msat'] for c in channels
              if c['state'] != 'CHANNELD_NORMAL'
              and c['state'] != 'CHANNELD_AWAITING_LOCKIN']
    if len(normal) > 0:
        r += "COMPLETE ({} channels fully open)".format(len(normal))
        stages['channels'] = True
    elif len(starting) > 0:
        r += "WORKING ({} channels opening)".format(len(starting))
    elif len(ending) > 0:
        r += "INCOMPLETE ({} channels closing)".format(len(ending))
    else:
        r += "INCOMPLETE: No channels open.  Try 'helpme channels'"

    r += "\nSTAGE 4 (making payments): "
    if len(payments) == 0:
        r += "INCOMPLETE: No payments made.  Try 'helpme pay'"
    elif len([s for s in payments if s['status'] == 'complete']) == 0:
        r += "INCOMPLETE (No payments succeeded)"
    else:
        r += "COMPLETE ({} payments made)".format(len([s for s in payments if s['status'] == 'complete']))
        stages['payments'] = True

    r += "\nSTAGE 5 (receiving payments): "
    if len(invoices) == 0:
        r += "INCOMPLETE: No payments made.  Try 'helpme invoice'"
    elif len([s for s in invoices if s['status'] == 'paid']) == 0:
        r += "INCOMPLETE (No payments succeeded)"
    else:
        r += "COMPLETE ({} payments received)".format(len([s for s in invoices if s['status'] == 'paid']))
        stages['invoices'] = True

    r += "\nSTAGE 6 (adding bling): "
    # We assume default config locations
    config = defaultdict(list)
    configfile_global = path.join(path.dirname(plugin.lightning_dir), "config")
    configfile_network = path.join(plugin.lightning_dir, "config")
    read_config(configfile_global, config)
    read_config(configfile_network, config)

    plugins = plugin.rpc.listconfigs()['plugins']

    if len(config) == 0:
        r += "No config file.  Try 'helpme bling'"
    elif 'alias' not in config and 'rgb' not in config:
        r += "You have not customized alias or color.  Try 'helpme bling'"
    # They pretty much need this plugin. pay, bcli, ... are in 'important-plugins'
    elif len(plugins) <= 1:
        r += "You have not added plugins.  Try 'helpme plugins'"
    else:
        r += "COMPLETE ({} plugins)".format(len(plugins))
        stages['plugins'] = True

    if all(v for v in stages.values()):
        r += """\n\nCONGRATULATIONS!

You can do anything from here!  Look up your node on an explorer, like:
"""
        for url in ['https://lightning.chaintools.io/node/'
                    'https://explore.casa/nodes/'
                    'https://explorer.acinq.co/n/'
                    'https://1ml.com/node/']:
            r += '   {}/{}\n'.format(url, info['id'])

        r += "\nYou can also try 'helpme history' to learn more about the lightning network"

    return r


def read_config(configfile, config):
    try:
        with open(configfile, encoding="utf-8") as f:
            for line in f:
                l2 = line.strip()
                if l2.startswith('#') or l2 == '':
                    continue
                parts = l2.split('=', 1)
                if len(parts) == 1:
                    parts.append(None)
                config[parts[0]].append(parts[1])
    except FileNotFoundError:
        pass


def color_dist(c1, c2):
    return ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2) ** 0.5


def closest_color(color, colors):
    best_dist = 0xFF * 3
    for c in colors:
        dist = color_dist(color, c)
        # Choose closest
        if dist < best_dist:
            best = c
            best_dist = dist

    return best, best_dist


# This is rough, but if you want to argue, write a better one :)
def describe_color(rgb):
    b = bytearray.fromhex(rgb)
    color = (b[0], b[1], b[2])

    # From https://wikipedia.org/wiki/Web_colors
    webcolors = ((0xFF, 0xFF, 0xFF, 'white'),
                 (0x00, 0x00, 0x00, 'black'),
                 (0xFF, 0x00, 0x00, 'red'),
                 (0x00, 0xFF, 0x00, 'lime'),
                 (0x00, 0x00, 0xFF, 'blue'),
                 (0xFF, 0xFF, 0x00, 'yellow'),
                 (0xC0, 0xC0, 0xC0, 'silver'),
                 (0x80, 0x80, 0x80, 'gray'),
                 (0x80, 0x00, 0x00, 'maroon'),
                 (0x80, 0x80, 0x00, 'olive'),
                 (0x00, 0x80, 0x00, 'green'),
                 (0x00, 0xFF, 0xFF, 'aqua'),
                 (0x00, 0x80, 0x80, 'teal'),
                 (0x00, 0x00, 0x80, 'navy'),
                 (0xFF, 0x00, 0xFF, 'fuchsia'),
                 (0x80, 0x00, 0x80, 'purple'))
    best, best_dist = closest_color(color, webcolors)

    # Are we exact?  We're done.
    if best_dist == 0:
        return best[3]

    # Are we really close?
    if best_dist < 0x10:
        return "off-" + best[3]

    # Use a tinge of a fundamental color.
    tinges = ((0xFF, 0xFF, 0xFF, 'light'),
              (0x00, 0x00, 0x00, 'dark'),
              (0xFF, 0x00, 0x00, 'reddish'),
              (0x00, 0xFF, 0x00, 'greenish'),
              (0x00, 0x00, 0xFF, 'blueish'))
    tinge = (0 if color[0] <= best[0] else 255,
             0 if color[1] <= best[1] else 255,
             0 if color[2] <= best[2] else 255)
    tinge, _ = closest_color(tinge, tinges)
    return tinge[3] + " " + best[3]


def give_bling_advice(plugin):
    config = plugin.rpc.listconfigs()
    return """Adding Bling

You can customize your node by giving it a fun name and favorite color!
It's currently called '{}' and its favorite color is '{}' ({})

There's a directory called '.lightning' in your home directory: if
there isn't one already, make a file called 'config'.

(You can read more detail by typing 'man lightningd-config').

Lines starting with # are comments.  Here's an example you can copy:

# A name we give our node, when we advertize channels.  The default
# one is generated from our public key, which is boring.  Anyone can
# call their node anything, so it's not secure, just fun!
alias=Flowers By Irene

# Favorite color is expressed as a hexidecimal number, see https://wikipedia.org/wiki/Web_colors
rgb=3f0000
""".format(config['alias'], config['rgb'], describe_color(config['rgb']))


def give_pay_advice(plugin, *args):
    if len(args) > 1:
        raise ValueError("Sorry, I can only give pay advice for one invoice at a time")

    peers = plugin.rpc.listpeers()['peers']
    live_channels = get_channel_list(peers)
    offline_funds = plugin.rpc.listfunds()['outputs']
    tot_off_funds = sum([f['amount_msat'] for f in offline_funds
                         if f['status'] == 'confirmed'])

    tot_on_funds = sum([c['spendable_msat'] for c in live_channels])
    max_spend = max([c['spendable_msat'] for c in live_channels],
                    default=Millisatoshi(0))

    if len(args) == 0:
        if len(live_channels) == 0:
            return "You need some active channels to pay an invoice: try 'helpme channels'"
        return """You can use the 'pay' command to pay an invoice; invoices start with 'ln;, and indicate how much to pay, and to whom, and describe what you're paying for.  You can decode an invoice with 'decodepay'.  You can pay up to {} at the moment, as that is the most funds you have available in a channel""".format(max_spend)

    if len(args) == 1:
        inv = plugin.rpc.decodepay(args[0])
        network = plugin.rpc.getinfo()['network']

        # Check we're on the right network.
        if inv['currency'] == 'bc' and network != 'bitcoin':
            return "This is an invoice for real bitcoin, but we're on {}.  See 'helpme mainnet'".format(network)
        if inv['currency'] == 'tb' and network == 'bitcoin':
            return "This is an invoice for testnet bitcoin, but we're using real bitcoin"

        if len(live_channels) == 0:
            return "We need some active channels to pay this invoice: see helpme channels {}".format(args[0])

        if 'amount_msat' not in inv:
            if tot_on_funds == 0:
                return "You don't have any spendable channels, so you can't pay the invoice"
            amount = '1msat'
        else:
            if max_spend <= inv['amount_msat']:
                if tot_off_funds < inv['amount_msat']:
                    return "You don't have enough in any one channel to pay this invoice of {}; you'll need more funds".format(inv['amount_msat'])
                else:
                    # Need reserve
                    return "You don't have enough in any one channel to pay this invoice of {}; open a new channel with at least {}".format(inv['amount_msat'],
                                                                                                                                            inv['amount_msat'] * 1.01)
            amount = inv['amount_msat']

        # Do we have any online peers?
        if not any([c for c in peers['connected']]):
            return "We're not connected to any peers.  Are we offline?"

        try:
            plugin.rpc.getroute(inv['payee'], amount, 1)
        except RpcError:
            return "You have channels with capacity, but I can't find a route to the recipient"

        if 'amount_msat' not in inv:
            return "You can pay this invoice with 'pay {} <amount>' where <amount> is between {} and {}".format(args[0], '1msat', max_spend)
        return "You can pay this invoice with 'pay {}'".format(args[0])


def give_invoice_advice(plugin, *args):
    lower = 1
    upper = 10000000
    while lower < upper:
        num = int((lower) / 2)
        if plugin.rpc.listinvoices('inv-' + str(num))['invoices'] != []:
            lower = num + 1
        else:
            upper = num

    live_channels = get_channel_list(plugin.rpc.listpeers()['peers'])

    max_incoming = max([c['to_us_msat'] - c['our_reserve_msat'] for c in live_channels],
                       default=Millisatoshi(0))
    if max_incoming <= Millisatoshi(0):
        return """You can create an invoice, but have no incoming capacity, so it won't be payable.  Try 'helpme capacity'"""

    return """You can create an invoice with 'invoice <amount> <label> <description>
Where <amount> is up to {}, <label> can be any unique string like 'inv-{}', and 'description' is a note for your own reference

Note that the default expiry is 7 days, but you can change it: see 'man lightning-invoice' for all the options.""".format(max_incoming, num)


def give_channel_advice(plugin, *args):
    if len(args) > 1:
        raise ValueError("Sorry, I can only give channel advice for one invoice at a time")
    elif len(args) < 1:
        raise ValueError("I can only give channel advice if you specify an invoice")

    offline_funds = plugin.rpc.listfunds()['outputs']
    tot_off_funds = sum([f['amount_msat'] for f in offline_funds
                         if f['status'] == 'confirmed'])

    if len(args) == 1:
        inv = plugin.rpc.decodepay(args[0])
        network = plugin.rpc.getinfo()['network']

        # Check we're on the right network.
        if inv['currency'] == 'bc' and network != 'bitcoin':
            return "This is an invoice for real bitcoin, but we're on {}.  See 'helpme mainnet'".format(network)
        if inv['currency'] == 'tb' and network == 'bitcoin':
            return "This is an invoice for testnet bitcoin, but we're using real bitcoin"

        # Need reserve, (plus fees!)
        if 'amount_msat' in inv:
            if tot_off_funds < inv['amount_msat'] * 1.01:
                return "You'd need a channel of at least {} to pay this invoice, and you only have {}".format(inv['amount_msat'] * 1.01, tot_off_funds)

        nodes = plugin.rpc.listnodes(inv['payee'])['nodes']

        # FIXME: What if we have a channel already, but it's insufficient?
        if len(nodes) == 1:
            if nodes[0]['addresses'] != []:
                return "You can try opening a channel directly to pay this invoice: 'lightning-cli connect {}' then 'lightning-cli fundchannel {} {}'".format(inv['payee'], inv['payee'], inv['amount_msat'])

            # Find a likely neighbor.
            channels = plugin.rpc.listchannels(source=inv['payee'])['channels']
            candidates = [(c['destination'], c['amount_msat'] - inv['amount_msat'])
                          for c in channels
                          if c['active'] and c['amount_msat'] > inv['amount_msat'] * 2]
            best = None
            for c in candidates:
                if not best or best[1] < c[1]:
                    best = c

            if best:
                return "You can try opening a channel to a neighbor to pay this invoice: 'lightning-cli connect {}' then 'lightning-cli fundchannel {} {}'".format(c[0], c[0], inv['amount_msat'])

            return "Sorry, I can't find an address for the node, and no neighbors seems likely to have capacity to pay either :("

        # Unknown node.
        return "FIXME: Parse invoice for a routehint as to how to reach this node!"

    # Look at unconnected peers for one with decent capacity.
    peers = [p for p in plugin.rpc.listpeers()['peers']
             if p['channels'] == []]

    best = None
    # Don't even bother if they don't have $10.
    best_score = Millisatoshi("0.001btc") * 2
    for p in peers:
        # FIXME: Filter out giant fee channels...
        channels = plugin.rpc.listchannels(source=inv['payee'])['channels']

        # Score by total capacity as well as max capacity.  Both matter.
        score = (sum([c['htlc_maximum_msat'] for c in channels])
                 + max([c['htlc_maximum_msat'] for c in channels],
                       default=Millisatoshi(0)))

        if score > best_score:
            best_score = score
            best = p

    advice = """You can create *channels* with other nodes to make payments.  It costs bitcoin to create a channel.  If you run 'helpme channels <invoice>' you can get advice on what channel you might want to create for that invoice.

Otherwise it's a good idea to pick a node with reasonable capacity who
has the coolest name!"""

    if best:
        advice += """ One of your peers seems like a good candidate to make a channel with.  Try:
        lightning-cli fundchannel {} all""".format(best['id'], best['id'])

    return advice


def give_peers_advice(plugin):
    peers = plugin.rpc.listpeers()['peers']

    if len(peers) == 0:
        return "I always try to connect to {} random peers, but that doesn't seem to have worked since we're connected to none.  Sorry.".format(DESIRED_PEERS)

    return """You can connect to peers with the 'connect' command: you can either use a peer id like '0204a2b95b4c208383d7f02e741a8bfd5b5b7e8bea8d1543b1255da8342d9f2c6b' and I'll try to look up the address, or add an address hint like '0204a2b95b4c208383d7f02e741a8bfd5b5b7e8bea8d1543b1255da8342d9f2c6b@127.0.0.1:9735'.

You can see what peers you're connected to right now with 'listpeers'.
"""


def give_funds_advice(plugin):
    return """You need money.  In the Good Old Days, you could use a bitcoin faucet to get a few bitcoin at a time, but these days it's actually worth something.

However, if you do find some bitcoin, you can send it to your lightning node quite easily.  To do that, get an address with 'lightning-cli newaddr all'.  That will give you an old-style address which starts with '3', or (better!) a new-style address which starts with 'bc1'."""


def give_shutdown_advice(plugin):
    return """You can type 'lightning-cli stop' to shut down your node.  But you don't need to, since it should handle getting killed at any time.

Beware that if your node is offline while channels are open, the other side of the channel can try to cheat you!  The default is 144 blocks (about 24 hours), but you can configure this by setting 'watchtime-blocks'."""


def give_plugin_advice(plugin):
    return """You can create plugins for Core-Lightning which do awesome things.  Like me, the 'helpme' plugin!  They can also, y'know, steal your lunch, so be careful!

There's a repository of useful plugins at https://github.com/lightningd/plugins

You can download them and add them to your 'config' file as
'plugin=/path/to/plugin', or put them all in a directory and use
'plugin-dir=/path/to/plugins' to load them all.  Then restart!"""


def give_mainnet_advice(plugin):
    network = plugin.rpc.getinfo()['network']
    if network == 'bitcoin':
        return """You are already on the main bitcoin network, so mistakes cost real money!"""

    return """To go onto the main network, you need to add 'network=bitcoin' to the config file, but it will refuse to start with existing non-mainnet files.  The best way is to move or delete your .lightning directory, then create a fresh one with 'network=bitcoin' in a '.lightning/config' and restart."""


def give_capacity_advice(plugin):
    return """If you need incoming capacity, there are a few ways to do it:

1. You can open a channel and use it to make a payment.  Note that 1% of the channel is generally kept in reserve by each side, so you'll need to spend more than 1%.

2. Someone can create a channel to you directly: if they open a channel they will be the one funding it.  This happens organically when people start buying and discover they can't pay you, but it causes delays and hassle.

3. There are a few free and paid services which will open channels to you.  A summary can be found at https://wiki.ion.radar.tech/tutorials/troubleshooting/bootstrapping-channels"""


def give_history_advice(plugin):
    return """Bitcoin developers have always known that bitcoin doesn't scale
well: it gets security by having every node see every transaction,
which is amazing but terribly slow.

It's also been known that not all bitcoin transactions need to be on
the bitcoin blockchain.  Satoshi (Bitcoin's inventor) included a way
of replacing transactions to allow incremental payments, but it didn't
work well.  Over the years others created more sophisticated systems,
up to "payment channels" which allowed you to pay a single user over
and over with only two onchain transactions.

In early 2015 Joseph Poon and Thaddeus Dryja released a paper called
the Lightning Network, which combined a new technique for
bi-directional channels with another idea called atomic-swaps, which
allows the channels to form a network where payments could be made
without a direct channel.

(Note: Christian Decker wrote a similar paper, but due to publication
delays it came out after the Lightning paper.  He's nice so I always
like to mention it).

You can read all about the details on the Bitcoin Wiki:

        https://en.bitcoin.it/wiki/Payment_channels

Anyway, the paper came out as Rusty Russell was joining Blockstream
and switching from almost 20 years of being a Linux Kernel developer
to this strange Bitcoin thing.  And they asked him to implement it, as
nobody else was; by mid-2016 there were three teams trying to
implement lightning, so they all met in Milan and started the first
"specification" for Lightning.

All three of those teams (ACINQ, Lightning Labs and Blockstream) are
still deeply involved in the specification process: we call the
documents BOLTs.  This is where major improvements to the protocol
come from:

        https://github.com/lightningnetwork/lightning-rfc

The last four years have been amazing; the developers working on
Lightning are dedicated to sharing a vision of amazing frictionless
payments.  We all compete on our implementations while cooperating on
interoperability and extending the specification.

The Lightning mottos are "It's OK to be odd!" and "Be excellent to
each other".  And we even have a theme song!

Good luck in your own journey!
Rusty Russell,
Senior Code Monkey."""


# Format hint `simple` makes lightning-cli print it as (-H) human readable
def format_simple(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        return {'text': fn(*args, **kwargs), 'format-hint': 'simple'}
    return wrapped


@plugin.method("helpme")
@format_simple
def helpme(plugin, command=None, *args):
    """Gives helpful hints about running this node."""

    if command is None:
        return give_general_advice(plugin)
    elif command == "bling":
        return give_bling_advice(plugin)
    elif command == "pay":
        return give_pay_advice(plugin, *args)
    elif command == "invoice":
        return give_invoice_advice(plugin, *args)
    elif command == "channels":
        return give_channel_advice(plugin)
    elif command == "peers":
        return give_peers_advice(plugin)
    elif command == "funds":
        return give_funds_advice(plugin)
    elif command == "shutdown":
        return give_shutdown_advice(plugin)
    elif command == "plugins":
        return give_plugin_advice(plugin)
    elif command == "history":
        return give_history_advice(plugin)
    elif command == "mainnet":
        return give_mainnet_advice(plugin)
    elif command == "capacity":
        return give_capacity_advice(plugin)

    raise ValueError("Unknown command {}".format(command))


# We try to connect to peers ourselves
class ConnectThread(threading.Thread):
    def __init__(self, nodes, peers_wanted):
        super().__init__()
        self.daemon = True
        self.nodes = nodes
        self.peers_wanted = peers_wanted
        self.start()

    def run(self):
        while self.peers_wanted > 0:
            k = random.choice(list(self.nodes.keys()))

            # Try each address.
            for a in self.nodes[k]:
                try:
                    plugin.rpc.connect(k, a['address'], a['port'])
                    del self.nodes[k]
                    self.peers_wanted -= 1
                    break
                except Exception:
                    pass


@plugin.init()
def init(options, configuration, plugin):
    rpchelp = plugin.rpc.help().get('help')
    # detect if server cli has moved `listpeers.channels[]` to `listpeerchannels`
    # See https://github.com/ElementsProject/lightning/pull/5825
    # TODO: replace by rpc version check once v23 is released
    plugin.listpeerchannels = False
    if len([c for c in rpchelp if c["command"].startswith("listpeerchannels ")]) != 0:
        plugin.listpeerchannels = True

    network = plugin.rpc.getinfo()['network']
    if network == 'regtest':
        plugin.log('Not seeking regtest peers', level='debug')
        return

    # Try to get some peers if we have less than 3.
    peers = plugin.rpc.listpeers()['peers']
    if sum([p['connected'] for p in peers]) >= DESIRED_PEERS:
        plugin.log('Already have >= {} peers connected, not seeking more'
                   .format(DESIRED_PEERS), level='debug')
        return

    # Maybe we know some from gossip?
    nodes = {}
    for n in plugin.rpc.listnodes()['nodes']:
        if 'addresses' in n and len(n['addresses']) > 0:
            nodes[n['nodeid']] = n['addresses']

    # Remove any peers we already have; we want fresh blood!
    for p in peers:
        if p['id'] in nodes:
            del nodes[p['id']]

    # If we don't have a significant number of choices, add canned ones.
    if len(nodes) < DESIRED_PEERS * 10:
        if network == 'bitcoin':
            nodes.update(known_nodes_mainnet)
        else:
            nodes.update(known_nodes_testnet)

    ConnectThread(nodes, DESIRED_PEERS)


if __name__ == '__main__':
    plugin.run()


# Test code.  I'm sure theres a way to put this in a separate file somehow.
def test_color_dist():
    assert color_dist((255, 255, 255), (0, 255, 255)) == 255
    assert color_dist((255, 255, 255), (255, 255, 255)) == 0
    assert color_dist((255, 255, 255), (255, 0, 255)) == 255
    assert color_dist((255, 255, 255), (255, 255, 0)) == 255


def test_closest_color():
    best, dist = closest_color((255, 255, 255), ((0, 255, 255),))
    assert best == (0, 255, 255)
    assert dist == 255
    best, dist = closest_color((255, 255, 255), ((0, 255, 255), (0, 0, 0)))
    assert best == (0, 255, 255)
    assert dist == 255
    best, dist = closest_color((255, 255, 255),
                               ((0, 255, 255),
                                (2, 255, 254),
                                (0, 0, 0)))
    assert best == (2, 255, 254)
    assert dist < 255


def test_describe_color():
    def color_to_name(c):
        return "{:02x}{:02x}{:02x}".format(c[0], c[1], c[2])

    table = ((0xFF, 0xFF, 0xFF, 'white'),
             (0x00, 0x00, 0x00, 'black'),
             (0xFF, 0x00, 0x00, 'red'),
             (0x00, 0xFF, 0x00, 'lime'),
             (0x00, 0x00, 0xFF, 'blue'),
             (0xFF, 0xFF, 0x00, 'yellow'),
             (0xC0, 0xC0, 0xC0, 'silver'),
             (0x80, 0x80, 0x80, 'gray'),
             (0x80, 0x00, 0x00, 'maroon'),
             (0x80, 0x80, 0x00, 'olive'),
             (0x00, 0x80, 0x00, 'green'),
             (0x00, 0xFF, 0xFF, 'aqua'),
             (0x00, 0x80, 0x80, 'teal'),
             (0x00, 0x00, 0x80, 'navy'),
             (0xFF, 0x00, 0xFF, 'fuchsia'),
             (0x80, 0x00, 0x80, 'purple'))

    for c in table:
        # Straight match
        assert describe_color(color_to_name(c)) == c[3]
        # Minor variant
        assert describe_color(color_to_name((c[0] ^ 1, c[1] ^ 2, c[2] ^ 3))) == "off-" + c[3]

        if c[0] < 0xFF:
            assert describe_color(color_to_name((c[0] + 0x11, c[1], c[2]))) == "reddish " + c[3]
        if c[1] < 0xFF:
            assert describe_color(color_to_name((c[0], c[1] + 0x11, c[2]))) == "greenish " + c[3]
        if c[2] < 0xFF:
            assert describe_color(color_to_name((c[0], c[1], c[2] + 0x11))) == "blueish " + c[3]
